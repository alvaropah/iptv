#!/usr/bin/env python3
import gzip
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path

M3U = Path("mi_playlist_final.m3u")
OUT = Path("guide.xml")
MISSING = Path("epg_missing.txt")

SOURCES = [
    ("EPGShare ES1", "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz"),
    ("IPTV-EPG España", "https://iptv-epg.org/files/epg-es.xml"),
]

def norm(value):
    """Normalise IDs/names so e.g. M+.Estrenos.es == movistarestrenos.es."""
    s = value or ""
    s = s.casefold()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.replace("&amp;", "and").replace("&", "and")
    s = s.replace("m+", "movistar").replace("m.", "movistar")
    s = re.sub(r"\bpor\s+movistar\b", "movistar", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

def clean_name(value):
    s = value or ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.casefold()
    s = re.sub(r"\b(uhd|fhd|fullhd|4k|hd|sd|hevc|h265|raw|vip|bar)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def fetch_xml(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 EPG builder"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b" or url.endswith(".gz"):
        data = gzip.decompress(data)
    return ET.fromstring(data)

def read_playlist():
    text = M3U.read_text(encoding="utf-8", errors="ignore")
    wanted = {}
    for line in text.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        m = re.search(r'tvg-id="([^"]*)"', line, re.I)
        if not m or not m.group(1).strip():
            continue
        tvgid = m.group(1).strip()
        display = line.split(",", 1)[1].strip() if "," in line else tvgid
        wanted.setdefault(norm(tvgid), {
            "id": tvgid,
            "name": display,
            "name_norm": clean_name(display),
        })
    return wanted

def channel_display_names(ch):
    names = []
    if ch.text:
        names.append(ch.text)
    for x in ch.findall("display-name"):
        if x.text:
            names.append(x.text)
    return names

def best_match(ch, wanted):
    cid = ch.get("id", "")
    # 1) Exact normalised ID match: safest.
    k = norm(cid)
    if k in wanted:
        return wanted[k]["id"], 1.0, "id"

    # 2) Match against display names.
    source_names = [clean_name(x) for x in channel_display_names(ch)]
    source_names = [x for x in source_names if x]
    if not source_names:
        return None, 0, ""

    best = (None, 0.0)
    for wk, info in wanted.items():
        target = info["name_norm"]
        if not target:
            continue
        for sn in source_names:
            if sn == target:
                return info["id"], 0.99, "name"
            score = SequenceMatcher(None, sn, target).ratio()
            if score > best[1]:
                best = (info["id"], score)

    # Conservative threshold to avoid assigning EPG from a wrong channel.
    if best[1] >= 0.90:
        return best[0], best[1], "fuzzy"
    return None, best[1], ""

def main():
    wanted = read_playlist()
    print(f"Encontrados {len(wanted)} tvg-id únicos en {M3U.name}")

    # user_id -> source channel id, source channel element
    mapping = {}
    source_programmes = []

    for name, url in SOURCES:
        print(f"\nFuente: {name}")
        try:
            root = fetch_xml(url)
        except Exception as e:
            print(f"  ERROR descargando fuente: {e}")
            continue

        hits = 0
        for ch in root.findall("channel"):
            user_id, score, method = best_match(ch, wanted)
            if not user_id:
                continue
            uk = norm(user_id)
            # Keep the first high-confidence mapping.
            if uk not in mapping or score > mapping[uk]["score"]:
                mapping[uk] = {
                    "user_id": user_id,
                    "source_id": ch.get("id", ""),
                    "channel": ch,
                    "score": score,
                    "method": method,
                }
                hits += 1

        # Save source root for programme pass.
        source_programmes.append((name, root))

        print(f"  Coincidencias: {hits}")

    out = ET.Element("tv", {
        "generator-info-name": "Custom EPG for alvaropah/iptv",
        "generator-info-url": "https://github.com/alvaropah/iptv",
    })

    # One channel element per user's tvg-id.
    for uk, item in sorted(mapping.items(), key=lambda x: x[1]["user_id"].casefold()):
        ch = item["channel"]
        newch = ET.Element("channel", {"id": item["user_id"]})
        for child in ch:
            newch.append(child)
        out.append(newch)

    seen_programmes = set()
    programme_count = 0

    for name, root in source_programmes:
        for p in root.findall("programme"):
            source_id = p.get("channel", "")
            # Find mapped user ID by source channel ID.
            user_id = None
            for item in mapping.values():
                if item["source_id"] == source_id:
                    user_id = item["user_id"]
                    break
            if not user_id:
                continue

            key = (
                norm(user_id),
                p.get("start", ""),
                p.get("stop", ""),
                "".join(p.itertext())[:500],
            )
            if key in seen_programmes:
                continue

            np = ET.Element("programme", dict(p.attrib))
            np.set("channel", user_id)
            for child in p:
                np.append(child)
            out.append(np)
            seen_programmes.add(key)
            programme_count += 1

    missing = sorted(
        [info["id"] for k, info in wanted.items() if k not in mapping],
        key=str.casefold,
    )
    MISSING.write_text(
        "\n".join(missing) + ("\n" if missing else ""),
        encoding="utf-8",
    )

    ET.indent(out, space="  ")
    ET.ElementTree(out).write(OUT, encoding="utf-8", xml_declaration=True)

    print(f"\nEPG generado: {len(mapping)}/{len(wanted)} canales")
    print(f"Programas: {programme_count}")
    print(f"Sin EPG: {len(missing)}")
    print(f"Archivo: {OUT}")

if __name__ == "__main__":
    main()
