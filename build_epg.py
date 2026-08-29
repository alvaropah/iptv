#!/usr/bin/env python3
import re
import xml.etree.ElementTree as ET
from pathlib import Path

M3U = Path("mi_playlist_final.m3u")
EPG_REPO = Path("epg-src")
CHANNELS_OUT = Path("custom.channels.xml")

CHANNEL_FILES = [
    EPG_REPO / "sites" / "orangetv.orange.es" / "orangetv.orange.es.channels.xml",
    EPG_REPO / "sites" / "movistarplus.es" / "movistarplus.es.channels.xml",
    EPG_REPO / "sites" / "guia.tv" / "guia.tv.channels.xml",
    EPG_REPO / "sites" / "programacion-tv.elpais.com" / "programacion-tv.elpais.com.channels.xml",
    EPG_REPO / "sites" / "mi.tv" / "mi.tv_es.channels.xml",
    EPG_REPO / "sites" / "pluto.tv" / "pluto.tv_es.channels.xml",
]

def get_wanted():
    text = M3U.read_text(encoding="utf-8", errors="ignore")
    ids = set(re.findall(r'tvg-id="([^"]+)"', text, re.I))
    return {x.casefold(): x for x in ids}

def main():
    wanted = get_wanted()
    print(f"Encontrados {len(wanted)} tvg-id únicos en {M3U.name}")

    root = ET.Element("channels")
    found = {}

    for path in CHANNEL_FILES:
        if not path.exists():
            print(f"Fuente no disponible: {path}")
            continue
        try:
            src = ET.parse(path).getroot()
        except Exception as e:
            print(f"Error leyendo {path}: {e}")
            continue

        hits = 0
        for ch in src.findall("channel"):
            xmltv_id = ch.get("xmltv_id", "")
            exact = wanted.get(xmltv_id.casefold())
            if not exact or exact.casefold() in found:
                continue

            newch = ET.Element("channel", {
                "site": ch.get("site", ""),
                "site_id": ch.get("site_id", ""),
                "lang": ch.get("lang", "es"),
                "xmltv_id": exact,
            })
            newch.text = ch.text or exact
            root.append(newch)
            found[exact.casefold()] = exact
            hits += 1

        print(f"{path.parent.name}: {hits} coincidencias")

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(CHANNELS_OUT, encoding="utf-8", xml_declaration=True)

    missing = [v for k, v in wanted.items() if k not in found]
    Path("epg_missing.txt").write_text(
        "\n".join(sorted(missing, key=str.casefold)) + ("\n" if missing else ""),
        encoding="utf-8"
    )

    print(f"\nCanales preparados para EPG: {len(found)}/{len(wanted)}")
    print(f"Sin fuente EPG encontrada: {len(missing)}")

if __name__ == "__main__":
    main()
