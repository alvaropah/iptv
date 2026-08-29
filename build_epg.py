#!/usr/bin/env python3
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

M3U = Path("mi_playlist_final.m3u")
SOURCE = "https://raw.githubusercontent.com/dracohe/COLOR/master/guide_IPTV_COLOR.xml"
OUT = Path("guide.xml")

def wanted_ids():
    text = M3U.read_text(encoding="utf-8", errors="ignore")
    ids = set(re.findall(r'tvg-id="([^"]+)"', text, re.I))
    return {x.casefold(): x for x in ids if x.strip()}

def main():
    wanted = wanted_ids()
    print(f"Encontrados {len(wanted)} tvg-id únicos en {M3U.name}")
    print(f"Descargando EPG: {SOURCE}")

    req = urllib.request.Request(SOURCE, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()

    root = ET.fromstring(data)
    out = ET.Element("tv", {
        "generator-info-name": "Custom EPG for alvaropah/iptv",
        "generator-info-url": "https://github.com/alvaropah/iptv"
    })

    matched = set()

    # Copy only channels whose id exactly matches one of the user's tvg-id.
    for ch in root.findall("channel"):
        cid = ch.get("id", "")
        exact = wanted.get(cid.casefold())
        if not exact or exact.casefold() in matched:
            continue
        newch = ET.Element("channel", dict(ch.attrib))
        newch.set("id", exact)
        for child in ch:
            newch.append(child)
        out.append(newch)
        matched.add(exact.casefold())

    # Copy programmes belonging to the matched channels.
    programme_count = 0
    for p in root.findall("programme"):
        cid = p.get("channel", "")
        exact = wanted.get(cid.casefold())
        if not exact or exact.casefold() not in matched:
            continue
        np = ET.Element("programme", dict(p.attrib))
        np.set("channel", exact)
        for child in p:
            np.append(child)
        out.append(np)
        programme_count += 1

    missing = sorted(
        [v for k, v in wanted.items() if k not in matched],
        key=str.casefold
    )
    Path("epg_missing.txt").write_text(
        "\n".join(missing) + ("\n" if missing else ""),
        encoding="utf-8"
    )

    ET.indent(out, space="  ")
    ET.ElementTree(out).write(OUT, encoding="utf-8", xml_declaration=True)

    print(f"EPG generado: {len(matched)}/{len(wanted)} canales")
    print(f"Programas: {programme_count}")
    print(f"Sin EPG: {len(missing)}")
    print("Archivo: guide.xml")

if __name__ == "__main__":
    main()
