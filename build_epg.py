#!/usr/bin/env python3
import re, gzip, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

M3U = Path("mi_playlist_final.m3u")
OUT = Path("guide.xml")

SOURCES = [
    ("TDTChannels", "https://www.tdtchannels.com/epg/TV.xml.gz"),
    ("IPTV-EPG España", "https://iptv-epg.org/files/epg-es.xml"),
    ("IPTV-org Movistar+", "https://iptv-org.github.io/epg/guides/es/movistarplus.es.xml"),
]

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 EPG builder"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b" or url.endswith(".gz"):
        data = gzip.decompress(data)
    return data

def get_ids():
    text = M3U.read_text(encoding="utf-8", errors="ignore")
    ids = set(re.findall(r'tvg-id="([^"]+)"', text, flags=re.I))
    return {x.lower(): x for x in ids}

def main():
    wanted = get_ids()
    print(f"Encontrados {len(wanted)} tvg-id únicos en {M3U.name}")

    channels = {}
    programmes = []
    seen = set()

    for name, url in SOURCES:
        try:
            print(f"\nFuente: {name}")
            root = ET.fromstring(fetch(url))

            matched = 0
            for ch in root.findall("channel"):
                cid = ch.get("id", "")
                exact = wanted.get(cid.lower())
                if exact:
                    matched += 1
                    newch = ET.Element("channel", {"id": exact})
                    for child in ch:
                        newch.append(child)
                    channels.setdefault(exact, newch)

            for p in root.findall("programme"):
                cid = p.get("channel", "")
                exact = wanted.get(cid.lower())
                if not exact:
                    continue
                key = (exact, p.get("start",""), p.get("stop",""),
                       "".join(p.itertext())[:300])
                if key in seen:
                    continue
                seen.add(key)
                np = ET.Element("programme", dict(p.attrib))
                np.set("channel", exact)
                for child in p:
                    np.append(child)
                programmes.append(np)

            print(f"  Coincidencias: {matched}")
        except Exception as e:
            print(f"  Error: {e}")

    root_out = ET.Element("tv", {
        "generator-info-name": "Custom EPG - alvaropah/iptv",
        "generator-info-url": "https://github.com/alvaropah/iptv"
    })

    for cid in sorted(channels):
        root_out.append(channels[cid])

    programmes.sort(key=lambda p: (p.get("channel",""), p.get("start","")))
    for p in programmes:
        root_out.append(p)

    tree = ET.ElementTree(root_out)
    ET.indent(tree, space="  ")
    tree.write(OUT, encoding="utf-8", xml_declaration=True)

    print(f"\nEPG generado: {len(channels)}/{len(wanted)} canales con programación")
    print(f"Programas: {len(programmes)}")
    print(f"Archivo: {OUT}")

if __name__ == "__main__":
    main()
