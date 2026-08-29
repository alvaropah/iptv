#!/usr/bin/env python3
import gzip
import re
import urllib.request
import xml.etree.ElementTree as ET
import unicodedata
from pathlib import Path

M3U = Path("mi_playlist_final.m3u")
OUT = Path("guide.xml")
MISSING = Path("epg_missing.txt")
MAPPING = Path("epg_mapping.txt")
DUPLICATES = Path("epg_duplicate_warnings.txt")

# Priority is intentional:
# 1) locally generated IPTV-org guides
# 2) EPGShare
# 3) IPTV-EPG España
#
# A source can only claim a channel once. More importantly, we NEVER use
# fuzzy matching: a similar-looking channel must not receive somebody else's
# programming.
LOCAL_SOURCES = [
    ("IPTV-org Movistar+", Path("epg-local/movistarplus.xml")),
    ("IPTV-org Orange TV", Path("epg-local/orangetv.xml")),
]
REMOTE_SOURCES = [
    ("EPGShare ES1", "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz"),
    ("IPTV-EPG España", "https://iptv-epg.org/files/epg-es.xml"),
]

# Explicit, high-confidence relationships only.
ALIASES = {
    "movistarclásicoses.es":["M+.Clásicos.es","M+ Clásicos","Movistar Clásicos"],
    "movistardcine.es":["M+.Cine.es","M+ Cine","Movistar Cine"],
    "movistardeporteses.es":["Movistar.Deportes.1.es","Movistar Deportes","M+.Deportes.es"],
    "movistardocumentaleses.es":["M+.Documentales.es","M+ Documentales","Movistar Documentales"],
    "movistarf1es.es":["M+.F1.es","M+ F1","Movistar F1"],
    "movistarhitses.es":["M+.Hits.es","M+ Hits","Movistar Hits"],
    "movistarindiees.es":["M+.Indie.es","M+ Indie","Movistar Indie"],
    "movistarlaliga.es":["M+.LALIGA.TV.es","M+ LALIGA","Movistar LALIGA"],
    "movistarlaliga1.es":["M+.LALIGA.1.es","M+ LALIGA 1"],
    "movistarlaliga2.es":["M+.LALIGA.2.es","M+ LALIGA 2"],
    "movistarlaliga3.es":["M+.LALIGA.3.es","M+ LALIGA 3"],
    "movistarlaliga4.es":["M+.LALIGA.4.es","M+ LALIGA 4"],
    "movistarlaliga5.es":["M+.LALIGA.5.es","M+ LALIGA 5"],
    "movistarorgulloes.es":["M+.Orgullo.es","M+ Orgullo"],
    "movistaroriginaleses.es":["M+.Originales.es","M+ Originales"],
    "movistarpluses.es.plus2":["Movistar.Plus+.2.es","Movistar Plus+ 2","M+ 2"],
    "movistarvamos2es.es":["M+.Vamos.2.es","M+ Vamos 2"],
    "mplusacción.es":["M+.Acción.es","M+ Acción","Movistar Acción"],
    "mplusclásicoses.es":["M+.Clásicos.es","M+ Clásicos","Movistar Clásicos"],
    "mpluscomediaes.es":["M+.Comedia.es","M+ Comedia","Movistar Comedia"],
    "mplusdeporteses.es":["M+.Deportes.es","M+ Deportes","Movistar Deportes"],
    "mplusestrenos.es":["M+.Estrenos.es","M+ Estrenos","Movistar Estrenos"],
    "mplusgolf2.es":["M+.Golf.2.es","M+ Golf 2","Movistar Golf 2"],
    "mplusgolfes.es":["M+.Golf.es","M+ Golf","Movistar Golf"],
    "mplusligadecampeones2.es":["M+.Liga.de.Campeones.2.es","M+ Liga de Campeones 2"],
    "mplusligadecampeones4es.es":["M+.Liga.de.Campeones.4.es","M+ Liga de Campeones 4"],
    "mlaliga2.es":["M+.LALIGA.2.es","M+ LALIGA 2"],
    "mlaliga3.es":["M+.LALIGA.3.es","M+ LALIGA 3"],
    "mligadecampeones.es":["M+.Liga.de.Campeones.es","M+ Liga de Campeones"],
    "mdeportes2.es":["M+.Deportes.2.es","M+ Deportes 2"],
    "mdeportes3.es":["M+.Deportes.3.es","M+ Deportes 3"],
    "mdramaes.es":["M+.Drama.es","M+ Drama"],
    "daznmotogpes.es":["DAZN.MotoGP.es","DAZN MotoGP","DAZN Moto GP"],
    "clanes.es":["Clan.TVE.es","Clan TVE","Clan"],
    "classicaes.es":["Classica.es","Classica"],
    "cnbces.es":["CNBC.Europe.es","CNBC Europe","CNBC"],
    "cnninternational.es":["CNN.International.es","CNN International"],
    "cnnintes.es":["CNN.International.es","CNN International"],
    "cocina.es":["Canal.Cocina.es","Canal Cocina"],
    "canaldecasa.es":["Canal.Decasa.es","Canal Decasa","Decasa"],
    "discoveryes.es":["Discovery.Channel.es","Discovery Channel","Discovery"],
    "dwenespañoles.es":["DW.Español.es","DW Español"],
    "elconfidenciales.es":["El.Confidencial.es","El Confidencial"],
    "elgaragetves.es":["El.Garage.TV.es","El Garage TV","El Garage"],
    "elpaíses.es":["El.País.es","El País"],
    "fdf.es":["FDF.es","Factoría de Ficción"],
    "galiciatv.es":["TV.Galicia.es","TVG.es","Galicia TV"],
    "tvgaliciaes.es":["TV.Galicia.es","TVG.es","Galicia TV"],
    "tvgtvgaliciaes.es":["TV.Galicia.es","TVG.es","Galicia TV"],
    "goltv.es":["GOL.TV.es","GOL TV"],
    "hittv.es":["HIT.TV.es","Hit TV","HIT TV"],
    "laligahypermotiontv.es":["LALIGA.HYPERMOTION.TV.es"],
    "laligahypermotiontv2.es":["LALIGA.HYPERMOTION.TV.2.es"],
    "laligahypermotiontv3.es":["LALIGA.HYPERMOTION.TV.3.es"],
    "motorvisiontv.es":["Motorvision.TV.es","MotorVision TV"],
    "natgeowildes.es":["Nat.Geo.Wild.es","National Geographic Wild","Nat Geo Wild"],
    "navarratves.es":["Navarra.TV.es","Navarra TV","Navarra Televisión"],
    "pocoyóes.es":["Pocoyó.es","Pocoyo","Pocoyó"],
    "redbulltv.es":["Red.Bull.TV.es","Red Bull TV"],
    "runtimeacciónes.es":["Runtime.Acción.es"],
    "runtimeclásicoses.es":["Runtime.Clásicos.es"],
    "runtimecomediaes.es":["Runtime.Comedia.es"],
    "runtimecrimenes.es":["Runtime.Crimen.es"],
    "runtimees.es":["Runtime.es"],
    "runtimeromancees.es":["Runtime.Romance.es"],
    "runtimethrillerplusterrores.es":["Runtime.Thriller.es","Runtime.Terror.es"],
    "sicinternacionales.es":["SIC.Internacional.es"],
    "sinfiltroses.es":["Sin.Filtros.es"],
    "squirreles.es":["Squirrel.es","Squirrel"],
    "surfchanneles.es":["Surf.Channel.es","Surf Channel"],
    "tdp.es":["Teledeporte.es","TDP","Teledeporte"],
    "telemadridintes.es":["Telemadrid.Internacional.es","Telemadrid"],
    "trtworld.es":["TRT.World.es","TRT World"],
    "tveinternacional.es.plus1":["TVE.Internacional.es","TVE Internacional"],
    "votv3cast.es":["TV3.es","TV3 Cataluña","TV3 Cat"],
    "324es.es":["324.es","3/24","324"],
    "acontrapluscine.es":["A.Contracorriente.es","A Contracorriente Cine","A Contracorriente"],
    "amcselektes.es":["AMC.Selekt.es","AMC Selekt"],
    "amcwestern.es":["AMC.Western.es","AMC Western"],
    "aragóntves.es":["Aragón.TV.es","Aragón TV"],
    "aragóntvintes.es":["Aragón.TV.Internacional.es","Aragón TV Internacional"],
    "bbcnews.es":["BBC.News.es","BBC News"],
    "bemadtv.es":["Be.Mad.es","Be Mad","bemad"],
    "canalextremadurasates.es":["Canal.Extremadura.SAT.es","Canal Extremadura"],
    "canalparlamentoes.es":["Canal.Parlamento.es","Canal Parlamento"],
    "canalsurandalucíaes.es":["Canal.Sur.Andalucía.es","Canal Sur Andalucía","Canal Sur"],
    "cinefeelgoodverditves.es":["Cine.Feel.Good.es","Cine Feel Good"],
    "gh24h1.es":["GH.24H.1.es","Gran Hermano 24H 1"],
    "gh24h2.es":["GH.24H.2.es","Gran Hermano 24H 2"],
    "la8mediterráneoes.es":["La.8.Mediterráneo.es","La8 Mediterráneo"],
    "mundoserieses.es":["Mundo.Series.es","Mundo Series"],
    "tpa7.es":["TPA.7.es","Asturias 7"],
    "tpa8es.es":["TPA.8.es","Asturias 8"],
    "tracelatina.es":["TRACE.Latina.es","Trace Latina"],
    "vivircongatoses.es":["Vivir.con.Gatos.es","Vivir con Gatos"],
    "viznertv.es":["Vizner.TV.es","Vizner TV"],
    "vodarktv.es":["Dark.es","VOD Dark"],
    "voodsea.es":["Odisea.es","VOD Odisea","Odisea"],
    "vosyfy.es":["Syfy.es","VOD Syfy","Syfy"],
}

def norm(s):
    s = s or ""
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().casefold()
    s = s.replace("&amp;","and").replace("&","and")
    s = re.sub(r"[^a-z0-9]+","",s)
    return s

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b" or url.endswith(".gz"):
        data = gzip.decompress(data)
    return ET.fromstring(data)

def read_m3u():
    result = {}
    for line in M3U.read_text(encoding="utf-8",errors="ignore").splitlines():
        if not line.startswith("#EXTINF"): continue
        m = re.search(r'tvg-id="([^"]+)"',line,re.I)
        if not m: continue
        uid = m.group(1).strip()
        if not uid: continue
        name = line.split(",",1)[1].strip() if "," in line else uid
        result.setdefault(norm(uid),{"id":uid,"name":name})
    return result

def aliases_for(info):
    vals = [info["id"], info["name"]]
    vals += ALIASES.get(info["id"], [])
    return {norm(v) for v in vals if v}

def match_exact(ch, wanted):
    src = {norm(ch.get("id",""))}
    src |= {norm(x.text) for x in ch.findall("display-name") if x.text}
    src.discard("")
    for key, info in wanted.items():
        if src & aliases_for(info):
            return key, "exact/alias"
    return None, ""

def load_local():
    roots = []
    for name, path in LOCAL_SOURCES:
        if not path.exists():
            print(f"Fuente local: {name} -> NO GENERADA")
            continue
        try:
            roots.append((name, ET.parse(path).getroot()))
            print(f"Fuente local: {name} -> OK")
        except Exception as e:
            print(f"Fuente local: {name} -> ERROR {e}")
    return roots

def main():
    wanted = read_m3u()
    print(f"Encontrados {len(wanted)} tvg-id únicos en {M3U.name}")

    # First load sources.
    roots = load_local()
    for name, url in REMOTE_SOURCES:
        print(f"\nFuente: {name}")
        try:
            root = fetch(url)
            roots.append((name, root))
            print("  Descarga OK")
        except Exception as e:
            print(f"  ERROR: {e}")

    # Build all exact candidates first, then resolve collisions.
    candidates = {k: [] for k in wanted}
    for source_name, root in roots:
        for ch in root.findall("channel"):
            key, method = match_exact(ch, wanted)
            if key is not None:
                candidates[key].append((source_name, ch, method))

    # Source priority.
    priority = {name:i for i,(name,_) in enumerate(LOCAL_SOURCES)}
    priority.update({"EPGShare ES1":2, "IPTV-EPG España":3})

    mappings = {}
    warnings = []

    for key, items in candidates.items():
        if not items:
            continue
        # Prefer earlier source, then prefer channel IDs that are an exact
        # normalized match to the requested tvg-id.
        requested = wanted[key]["id"]
        items = sorted(items, key=lambda x: (
            priority.get(x[0], 99),
            0 if norm(x[1].get("id","")) == norm(requested) else 1
        ))
        chosen = items[0]
        mappings[key] = {
            "user_id": requested,
            "source_id": chosen[1].get("id",""),
            "channel": chosen[1],
            "source": chosen[0],
            "method": chosen[2],
        }
        if len(items) > 1:
            warnings.append(
                f'{requested}: {len(items)} candidatos -> elegido {chosen[0]}:{chosen[1].get("id","")}'
            )

    out = ET.Element("tv", {
        "generator-info-name":"Custom EPG for alvaropah/iptv v8",
        "generator-info-url":"https://github.com/alvaropah/iptv"
    })

    for item in sorted(mappings.values(), key=lambda x:x["user_id"].casefold()):
        c = ET.Element("channel", {"id":item["user_id"]})
        for child in item["channel"]:
            c.append(child)
        out.append(c)

    # Each source channel can only be mapped to ONE requested channel.
    # This is the critical anti-duplication guard.
    source_to_user = {}
    for key,item in mappings.items():
        skey = (item["source"], item["source_id"])
        if skey in source_to_user and source_to_user[skey] != item["user_id"]:
            warnings.append(
                f'REUSED SOURCE CHANNEL: {item["source"]}:{item["source_id"]} -> '
                f'{source_to_user[skey]} AND {item["user_id"]}'
            )
        else:
            source_to_user[skey] = item["user_id"]

    seen_programs = set()
    programs = 0
    for source_name, root in roots:
        for p in root.findall("programme"):
            uid = source_to_user.get((source_name, p.get("channel","")))
            if not uid:
                continue
            key = (
                uid.casefold(),
                p.get("start",""),
                p.get("stop",""),
                ET.tostring(p, encoding="unicode")
            )
            if key in seen_programs:
                continue
            seen_programs.add(key)
            np = ET.Element("programme", dict(p.attrib))
            np.set("channel", uid)
            for child in p:
                np.append(child)
            out.append(np)
            programs += 1

    missing = sorted(
        [info["id"] for key,info in wanted.items() if key not in mappings],
        key=str.casefold
    )
    MISSING.write_text("\n".join(missing)+("\n" if missing else ""),encoding="utf-8")
    MAPPING.write_text(
        "\n".join(
            f'{i["user_id"]} -> {i["source_id"]} | {i["source"]} | {i["method"]}'
            for i in sorted(mappings.values(), key=lambda x:x["user_id"].casefold())
        ) + ("\n" if mappings else ""),
        encoding="utf-8"
    )
    DUPLICATES.write_text(
        "\n".join(warnings)+("\n" if warnings else ""),
        encoding="utf-8"
    )

    ET.indent(out, space="  ")
    ET.ElementTree(out).write(OUT, encoding="utf-8", xml_declaration=True)

    print(f"\nEPG generado: {len(mappings)}/{len(wanted)} canales")
    print(f"Programas: {programs}")
    print(f"Sin EPG: {len(missing)}")
    print(f"Advertencias de matching: {len(warnings)}")
    print("Archivos: guide.xml, epg_missing.txt, epg_mapping.txt, epg_duplicate_warnings.txt")

if __name__ == "__main__":
    main()
