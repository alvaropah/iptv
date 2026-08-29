#!/usr/bin/env python3
import gzip
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from difflib import SequenceMatcher

M3U = Path("mi_playlist_final.m3u")
OUT = Path("guide.xml")
MISSING = Path("epg_missing.txt")
MAPPING = Path("epg_mapping.txt")

SOURCES = [
    ("EPGShare ES1", "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz"),
    ("IPTV-EPG España", "https://iptv-epg.org/files/epg-es.xml"),
]

# For channels whose tvg-id is not written like the EPG provider's
# display name, give the matcher explicit alternatives.
ALIASES = {
    "movistarclásicoses.es": ["M+. Clásicos", "M+ Clásicos", "Movistar Clásicos"],
    "movistardcine.es": ["M+. Cine", "M+ Cine", "Movistar Cine"],
    "movistardeporteses.es": ["Movistar Deportes", "M+. Deportes", "M+ Deportes"],
    "movistardocumentaleses.es": ["M+. Documentales", "M+ Documentales", "Movistar Documentales"],
    "movistarf1es.es": ["M+ F1", "M+. F1", "Movistar F1"],
    "movistarhitses.es": ["M+ Hits", "M+. Hits", "Movistar Hits"],
    "movistarindiees.es": ["M+ Indie", "M+. Indie", "Movistar Indie"],
    "movistarlaliga.es": ["M+ LALIGA", "M+. LALIGA", "Movistar LALIGA"],
    "movistarlaliga1.es": ["M+ LALIGA 1", "M+. LALIGA 1", "Movistar LALIGA 1"],
    "movistarlaliga2.es": ["M+ LALIGA 2", "M+. LALIGA 2", "Movistar LALIGA 2"],
    "movistarlaliga3.es": ["M+ LALIGA 3", "M+. LALIGA 3", "Movistar LALIGA 3"],
    "movistarlaliga4.es": ["M+ LALIGA 4", "M+. LALIGA 4", "Movistar LALIGA 4"],
    "movistarlaliga5.es": ["M+ LALIGA 5", "M+. LALIGA 5", "Movistar LALIGA 5"],
    "movistarorgulloes.es": ["M+ Orgullo", "Movistar Orgullo"],
    "movistaroriginaleses.es": ["M+ Originales", "Movistar Originales"],
    "movistarpluses.es.plus2": ["Movistar Plus+ 2", "Movistar Plus 2", "M+ 2"],
    "movistarvamos2es.es": ["M+ Vamos 2", "Movistar Vamos 2"],
    "mplusacción.es": ["M+ Acción", "M+. Acción", "Movistar Acción"],
    "mplusclásicoses.es": ["M+ Clásicos", "M+. Clásicos", "Movistar Clásicos"],
    "mpluscomediaes.es": ["M+ Comedia", "M+. Comedia", "Movistar Comedia"],
    "mplusdeporteses.es": ["M+ Deportes", "M+. Deportes", "Movistar Deportes"],
    "mplusestrenos.es": ["M+ Estrenos", "M+. Estrenos", "Movistar Estrenos"],
    "mplusgolf2.es": ["M+ Golf 2", "M+. Golf 2", "Movistar Golf 2"],
    "mplusgolfes.es": ["M+ Golf", "M+. Golf", "Movistar Golf"],
    "mplusligadecampeones2.es": ["M+ Liga de Campeones 2", "M+. Liga de Campeones 2"],
    "mplusligadecampeones4es.es": ["M+ Liga de Campeones 4", "M+. Liga de Campeones 4"],
    "daznmotogpes.es": ["DAZN MotoGP", "DAZN Moto GP"],
    "clanes.es": ["Clan TVE", "Clan", "Clan TV"],
    "canalhollywood.es": ["Canal Hollywood", "C. Hollywood"],
    "cnbces.es": ["CNBC Europe", "CNBC"],
    "cnninternational.es": ["CNN International"],
    "cnnintes.es": ["CNN International"],
    "cocina.es": ["Canal Cocina", "Cocina"],
    "canaldecasa.es": ["Canal Decasa", "Decasa"],
    "discoveryes.es": ["Discovery Channel", "Discovery"],
    "discoverychannel.es": ["Discovery Channel", "Discovery"],
    "dwenespañoles.es": ["DW Español", "DW Español"],
    "elconfidenciales.es": ["El Confidencial"],
    "elgaragetves.es": ["El Garage TV", "El Garage"],
    "elpaíses.es": ["El País"],
    "fdf.es": ["Factoría de Ficción", "FDF"],
    "filmcoes.es": ["Film&Co", "Filmco"],
    "galiciatv.es": ["TV Galicia", "Galicia TV", "TVG"],
    "tvgaliciaes.es": ["TV Galicia", "Galicia TV", "TVG"],
    "tvgtvgaliciaes.es": ["TV Galicia", "Galicia TV", "TVG"],
    "gh24h1.es": ["GH 24H 1", "Gran Hermano 24H 1", "GH24H1"],
    "gh24h2.es": ["GH 24H 2", "Gran Hermano 24H 2", "GH24H2"],
    "goltv.es": ["GOL TV", "Gol"],
    "hittv.es": ["Hit TV", "HIT TV"],
    "itaavanzadoes.es": ["Italiano Avanzado"],
    "itaintermedioes.es": ["Italiano Intermedio"],
    "itaprincipiantees.es": ["Italiano Principiante"],
    "la8mediterráneoes.es": ["La 8 Mediterráneo", "La8 Mediterráneo"],
    "laligahypermotiontv.es": ["LALIGA HYPERMOTION TV"],
    "laligahypermotiontv2.es": ["LALIGA HYPERMOTION TV 2"],
    "laligahypermotiontv3.es": ["LALIGA HYPERMOTION TV 3"],
    "maxavances.es": ["Max Avances", "Max"],
    "mdeportes2.es": ["M+ Deportes 2", "Movistar Deportes 2"],
    "mdeportes3.es": ["M+ Deportes 3", "Movistar Deportes 3"],
    "mdramaes.es": ["M+ Drama", "Movistar Drama"],
    "mlaliga2.es": ["M+ LALIGA 2", "M+. LALIGA 2"],
    "mlaliga3.es": ["M+ LALIGA 3", "M+. LALIGA 3"],
    "mligadecampeones.es": ["M+ Liga de Campeones", "M+. Liga de Campeones"],
    "motorvisiontv.es": ["Motorvision TV", "MotorVision"],
    "mundo_serieses.es": ["Mundo Series"],
    "mundoserieses.es": ["Mundo Series"],
    "natgeowildes.es": ["Nat Geo Wild", "National Geographic Wild"],
    "navarratves.es": ["Navarra TV", "Navarra Televisión"],
    "pocoyóes.es": ["Pocoyó", "Pocoyo"],
    "redbulltv.es": ["Red Bull TV", "RedBull TV"],
    "runtimeacciónes.es": ["Runtime Acción"],
    "runtimeclásicoses.es": ["Runtime Clásicos"],
    "runtimecomediaes.es": ["Runtime Comedia"],
    "runtimecrimenes.es": ["Runtime Crimen"],
    "runtimees.es": ["Runtime"],
    "runtimeromancees.es": ["Runtime Romance"],
    "runtimethrillerplusterrores.es": ["Runtime Thriller", "Runtime Terror"],
    "sicinternacionales.es": ["SIC Internacional"],
    "sinfiltroses.es": ["Sin Filtros"],
    "squirreles.es": ["Squirrel"],
    "surfchanneles.es": ["Surf Channel"],
    "tdp.es": ["Teledeporte", "TDP"],
    "telemadridintes.es": ["Telemadrid Internacional", "Telemadrid Int"],
    "tpa7.es": ["TPA 7", "Asturias 7"],
    "tpa8es.es": ["TPA 8", "Asturias 8"],
    "tracelatina.es": ["Trace Latina", "TRACE Latina"],
    "trtworld.es": ["TRT World"],
    "tveinternacional.es.plus1": ["TVE Internacional", "TVE Internacional +1"],
    "vivircongatoses.es": ["Vivir con Gatos"],
    "viznertv.es": ["Vizner TV"],
    "vodarktv.es": ["Dark", "VOD Dark"],
    "voodsea.es": ["Odisea", "VOD Odisea"],
    "vosyfy.es": ["Syfy", "VOD Syfy"],
    "votv3cast.es": ["TV3", "TV3 Cataluña", "TV3 Cat"],
    "324es.es": ["3/24", "324"],
    "acontrapluscine.es": ["A Contracorriente", "A Contracorriente Cine"],
    "alquiler1es.es": ["Alquiler 1", "Taquilla 1"],
    "amcselektes.es": ["AMC Selekt"],
    "amcwestern.es": ["AMC Western"],
    "aragóntves.es": ["Aragón TV"],
    "aragóntvintes.es": ["Aragón TV Internacional", "Aragón TV Int"],
    "bbcnews.es": ["BBC News"],
    "bemadtv.es": ["Be Mad", "bemad"],
    "canalextremadurasates.es": ["Canal Extremadura SAT"],
    "canalparlamentoes.es": ["Canal Parlamento"],
    "canalsurandalucíaes.es": ["Canal Sur Andalucía"],
    "cinefeelgoodverditves.es": ["Cine Feel Good"],
}

def norm(s):
    s = s or ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().casefold()
    s = s.replace("&amp;", "and").replace("&", "and")
    s = re.sub(r"[\+\.\-_/|:]+", " ", s)
    s = re.sub(r"\bmovistar\s*plus\b", "movistar", s)
    s = re.sub(r"\bm\s*\+\b", "mplus", s)
    s = re.sub(r"\bm\s*\.\b", "mplus", s)
    s = re.sub(r"\bmovistar\b", "movistar", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b" or url.endswith(".gz"):
        data = gzip.decompress(data)
    return ET.fromstring(data)

def playlist():
    text = M3U.read_text(encoding="utf-8", errors="ignore")
    result = {}
    for line in text.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line, re.I)
        if not m:
            continue
        uid = m.group(1).strip()
        if not uid:
            continue
        name = line.split(",", 1)[1].strip() if "," in line else uid
        result[norm(uid)] = {"id": uid, "name": name}
    return result

def channel_names(ch):
    out = []
    if ch.text:
        out.append(ch.text)
    out.extend(x.text for x in ch.findall("display-name") if x.text)
    return out

def candidate_names(info):
    vals = [info["id"], info["name"]]
    vals += ALIASES.get(info["id"], [])
    return {norm(x) for x in vals if x}

def match_channel(ch, wanted):
    source_vals = {norm(ch.get("id", ""))}
    source_vals |= {norm(x) for x in channel_names(ch) if x}
    source_vals.discard("")

    # Exact normalized ID/name/alias.
    for k, info in wanted.items():
        if source_vals & candidate_names(info):
            return k, 1.0, "exact"

    # Conservative fuzzy matching against explicit aliases and display name.
    best = (None, 0.0)
    for k, info in wanted.items():
        targets = candidate_names(info)
        for sv in source_vals:
            for tv in targets:
                score = SequenceMatcher(None, sv, tv).ratio()
                if score > best[1]:
                    best = (k, score)

    if best[1] >= 0.93:
        return best[0], best[1], "fuzzy"
    return None, 0, ""

def main():
    wanted = playlist()
    print(f"Encontrados {len(wanted)} tvg-id únicos en {M3U.name}")

    mappings = {}
    sources = []

    for source_name, url in SOURCES:
        print(f"\nFuente: {source_name}")
        try:
            root = fetch(url)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        hits = 0
        for ch in root.findall("channel"):
            key, score, method = match_channel(ch, wanted)
            if key is None:
                continue
            if key not in mappings or score > mappings[key]["score"]:
                mappings[key] = {
                    "user_id": wanted[key]["id"],
                    "source_id": ch.get("id", ""),
                    "channel": ch,
                    "score": score,
                    "method": method,
                    "source": source_name,
                }
                hits += 1

        sources.append((source_name, root))
        print(f"  Coincidencias: {hits}")

    out = ET.Element("tv", {
        "generator-info-name": "Custom EPG for alvaropah/iptv v5",
        "generator-info-url": "https://github.com/alvaropah/iptv",
    })

    for item in sorted(mappings.values(), key=lambda x: x["user_id"].casefold()):
        ch = item["channel"]
        newch = ET.Element("channel", {"id": item["user_id"]})
        for child in ch:
            newch.append(child)
        out.append(newch)

    # Index source_id -> our final tvg-id.
    source_map = {}
    for item in mappings.values():
        source_map.setdefault((item["source"], item["source_id"]), item["user_id"])

    seen = set()
    programs = 0
    for source_name, root in sources:
        for p in root.findall("programme"):
            user_id = source_map.get((source_name, p.get("channel", "")))
            if not user_id:
                continue
            key = (user_id.casefold(), p.get("start",""), p.get("stop",""), "".join(p.itertext())[:400])
            if key in seen:
                continue
            seen.add(key)
            np = ET.Element("programme", dict(p.attrib))
            np.set("channel", user_id)
            for child in p:
                np.append(child)
            out.append(np)
            programs += 1

    missing = [info["id"] for k, info in wanted.items() if k not in mappings]
    missing.sort(key=str.casefold)
    MISSING.write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")

    mapping_lines = []
    for item in sorted(mappings.values(), key=lambda x: x["user_id"].casefold()):
        mapping_lines.append(
            f'{item["user_id"]} -> {item["source_id"]} | {item["source"]} | {item["method"]}'
        )
    MAPPING.write_text("\n".join(mapping_lines) + ("\n" if mapping_lines else ""), encoding="utf-8")

    ET.indent(out, space="  ")
    ET.ElementTree(out).write(OUT, encoding="utf-8", xml_declaration=True)

    print(f"\nEPG generado: {len(mappings)}/{len(wanted)} canales")
    print(f"Programas: {programs}")
    print(f"Sin EPG: {len(missing)}")
    print("Archivos: guide.xml, epg_missing.txt, epg_mapping.txt")

if __name__ == "__main__":
    main()
