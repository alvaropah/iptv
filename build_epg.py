#!/usr/bin/env python3
import gzip
import re
import urllib.request
import xml.etree.ElementTree as ET
import unicodedata
from pathlib import Path
from collections import defaultdict

M3U = Path("mi_playlist_final.m3u")
OUT = Path("guide.xml")
MISSING = Path("epg_missing.txt")
MAPPING = Path("epg_mapping.txt")
CANDIDATES = Path("epg_candidates.txt")
WARNINGS = Path("epg_duplicate_warnings.txt")

LOCAL_SOURCES = [
    ("IPTV-org Movistar+", Path("epg-local/movistarplus.xml")),
    ("IPTV-org Orange TV", Path("epg-local/orangetv.xml")),
]
REMOTE_SOURCES = [
    ("EPGShare ES1", "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz"),
    ("IPTV-EPG España", "https://iptv-epg.org/files/epg-es.xml"),
]

# Only high-confidence aliases. No generic fuzzy matching.
ALIASES = {
    "movistarclásicoses.es":["M+.Clásicos.es","M+ Clásicos","Movistar Clásicos"],
    "movistardcine.es":["M+.Cine.es","M+ Cine","Movistar Cine"],
    "movistardeporteses.es":["M+.Deportes.es","Movistar Deportes","M+ Deportes"],
    "movistardocumentaleses.es":["M+.Documentales.es","M+ Documentales"],
    "movistarf1es.es":["M+.F1.es","M+ F1"],
    "movistarhitses.es":["M+.Hits.es","M+ Hits"],
    "movistarindiees.es":["M+.Indie.es","M+ Indie"],
    "movistarlaliga.es":["M+.LALIGA.TV.es","M+ LALIGA"],
    "movistarlaliga1.es":["M+.LALIGA.1.es","M+ LALIGA 1"],
    "movistarlaliga2.es":["M+.LALIGA.2.es","M+ LALIGA 2"],
    "movistarlaliga3.es":["M+.LALIGA.3.es","M+ LALIGA 3"],
    "movistarlaliga4.es":["M+.LALIGA.4.es","M+ LALIGA 4"],
    "movistarlaliga5.es":["M+.LALIGA.5.es","M+ LALIGA 5"],
    "movistarorgulloes.es":["M+.Orgullo.es","M+ Orgullo"],
    "movistaroriginaleses.es":["M+.Originales.es","M+ Originales"],
    "movistarpluses.es.plus2":["MovistarPlus+2.es","Movistar Plus+ 2"],
    "movistarvamos2es.es":["M+.Vamos.2.es","M+ Vamos 2"],
    "mplusacción.es":["M+.Acción.es","M+ Acción"],
    "mplusclásicoses.es":["M+.Clásicos.es","M+ Clásicos"],
    "mpluscomediaes.es":["M+.Comedia.es","M+ Comedia"],
    "mplusdeporteses.es":["M+.Deportes.es","M+ Deportes"],
    "mplusestrenos.es":["M+.Estrenos.es","M+ Estrenos"],
    "mplusgolf2.es":["M+.Golf.2.es","M+ Golf 2"],
    "mplusgolfes.es":["M+.Golf.es","M+ Golf"],
    "mplusligadecampeones2.es":["M+.Liga.de.Campeones.2.es","M+ Liga de Campeones 2"],
    "mplusligadecampeones4es.es":["M+.Liga.de.Campeones.4.es","M+ Liga de Campeones 4"],
    "mlaliga2.es":["M+.LALIGA.2.es","M+ LALIGA 2"],
    "mlaliga3.es":["M+.LALIGA.3.es","M+ LALIGA 3"],
    "mligadecampeones.es":["M+.Liga.de.Campeones.es","M+ Liga de Campeones"],
    "mdeportes2.es":["M+.Deportes.2.es","M+ Deportes 2"],
    "mdeportes3.es":["M+.Deportes.3.es","M+ Deportes 3"],
    "mdeportes4.es":["M+.Deportes.4.es","M+ Deportes 4"],
    "mdeportes5.es":["M+.Deportes.5.es","M+ Deportes 5"],
    "mdramaes.es":["M+.Drama.es","M+ Drama"],
    "daznmotogpes.es":["DAZN.MotoGP.es","DAZN MotoGP"],
    "clanes.es":["Clan.TVE.es","Clan TVE","Clan"],
    "classicaes.es":["Classica.es","Classica"],
    "cnbces.es":["CNBC.Europe.es","CNBC Europe","CNBC"],
    "cnninternational.es":["CNN.International.es","CNN International"],
    "cnnintes.es":["CNN.International.es","CNN International"],
    "cocina.es":["Canal.Cocina.es","Canal Cocina"],
    "canaldecasa.es":["Decasa.es","Canal Decasa"],
    "discoveryes.es":["Discovery.Channel.es","Discovery Channel"],
    "dwenespañoles.es":["DW.Español.es","DW Español"],
    "elconfidenciales.es":["El.Confidencial.es","El Confidencial"],
    "elgaragetves.es":["El.Garage.TV.es","El Garage TV"],
    "elpaíses.es":["El.País.es","El País"],
    "fdf.es":["FDF.es","FDFIC","Factoría de Ficción"],
    "factoríadeficción.es":["FactoriadeFiccion.es"],
    "galiciatv.es":["TV.Galicia.es","TVG.es","Galicia TV"],
    "tvgaliciaes.es":["TV.Galicia.es","TVG.es","Galicia TV"],
    "tvgtvgaliciaes.es":["TV.Galicia.es","TVG.es","Galicia TV"],
    "goltv.es":["GOL.TV.es","GOL TV"],
    "hittv.es":["HIT.TV.es","Hit TV"],
    "laligahypermotiontv.es":["LALIGA.HYPERMOTION.TV.es"],
    "laligahypermotiontv2.es":["LALIGA.HYPERMOTION.TV.2.es"],
    "laligahypermotiontv3.es":["LALIGA.HYPERMOTION.TV.3.es"],
    "motorvisiontv.es":["Motorvision.TV.es","MotorVision TV"],
    "natgeowildes.es":["Nat.Geo.Wild.es","National Geographic Wild"],
    "navarratves.es":["Navarra.Televisión.es","Navarra TV"],
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
    "squirreles.es":["Squirrel.es"],
    "surfchanneles.es":["Surf.Channel.es","Surf Channel"],
    "tdp.es":["Teledeporte.es","TDP","Teledeporte"],
    "telemadridintes.es":["Telemadrid.Internacional.es","Telemadrid"],
    "trtworld.es":["TRT.World.es","TRT World"],
    "tveinternacional.es.plus1":["TVE.Internacional.es","TVE Internacional"],
    "votv3cast.es":["TV3.es","TV3 Cataluña","TV3 Cat"],
    "324es.es":["324.es","3/24","324"],
    "acontrapluscine.es":["A.Contracorriente.es","A Contracorriente Cine"],
    "amcselektes.es":["AMC.Selekt.es","AMC Selekt"],
    "amcwestern.es":["AMC.Western.es","AMC Western"],
    "aragóntves.es":["Aragón.TV.es","Aragón TV"],
    "aragóntvintes.es":["Aragón.TV.Internacional.es","Aragón TV Internacional"],
    "bbcnews.es":["BBC.News.es","BBC News"],
    "bemadtv.es":["Be.Mad.es","Be Mad","BEMAD"],
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
    "tracelatinaes.es":["TraceLatina.fr@SD","Trace Latina"],
    "tracelatina.es":["TraceLatina.fr@SD","Trace Latina"],
    "vivircongatoses.es":["Vivir.con.Gatos.es"],
    "viznertv.es":["Vizner.TV.es","Vizner TV"],
    "vodarktv.es":["Dark.es","VOD Dark"],
    "voodsea.es":["Odisea.es","VOD Odisea","Odisea"],
    "vosyfy.es":["SCI-FI","Syfy.es","VOD Syfy","Syfy"],
}

def norm(s):
    s = s or ""
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().casefold()
    s = s.replace("&amp;","and").replace("&","and")
    return re.sub(r"[^a-z0-9]+","",s)

def fetch(url):
    req = urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=180) as r:
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

def wanted_names(info):
    vals = [info["id"], info["name"]] + ALIASES.get(info["id"], [])
    return {norm(x) for x in vals if x}

def source_names(ch):
    vals = [ch.get("id","")] + [x.text for x in ch.findall("display-name") if x.text]
    return {norm(x) for x in vals if x}

def exact_candidates(wanted, root):
    found = defaultdict(list)
    for ch in root.findall("channel"):
        src = source_names(ch)
        if not src: continue
        for key, info in wanted.items():
            if src & wanted_names(info):
                found[key].append(ch)
    return found

def load_sources():
    roots=[]
    for name,path in LOCAL_SOURCES:
        if path.exists():
            try:
                roots.append((name,ET.parse(path).getroot()))
                print(f"Fuente local: {name} -> OK")
            except Exception as e:
                print(f"Fuente local: {name} -> ERROR {e}")
        else:
            print(f"Fuente local: {name} -> NO GENERADA")
    for name,url in REMOTE_SOURCES:
        print(f"Fuente: {name}")
        try:
            roots.append((name,fetch(url)))
            print("  Descarga OK")
        except Exception as e:
            print(f"  ERROR: {e}")
    return roots

def main():
    wanted = read_m3u()
    print(f"tvg-id únicos: {len(wanted)}")
    roots = load_sources()

    # Gather all exact/alias candidates.
    all_candidates = {k:[] for k in wanted}
    for source_name,root in roots:
        cands=exact_candidates(wanted,root)
        for k,chs in cands.items():
            for ch in chs:
                all_candidates[k].append((source_name,ch))

    priority = {name:i for i,(name,_) in enumerate(LOCAL_SOURCES)}
    priority.update({"EPGShare ES1":2,"IPTV-EPG España":3})

    mappings={}
    candidate_lines=[]
    warnings=[]

    # Resolve one requested tvg-id at a time.
    for key,items in all_candidates.items():
        if not items: continue
        requested=wanted[key]["id"]

        # Prefer source priority. Within a source prefer exact ID over alias.
        items.sort(key=lambda x:(
            priority.get(x[0],99),
            0 if norm(x[1].get("id",""))==norm(requested) else 1
        ))
        chosen=items[0]
        mappings[key]={
            "user_id":requested,
            "source_id":chosen[1].get("id",""),
            "channel":chosen[1],
            "source":chosen[0],
        }

        if len(items)>1:
            candidates_txt=" ; ".join(f"{s}:{c.get('id','')}" for s,c in items)
            candidate_lines.append(f"{requested} | ELEGIDO {chosen[0]}:{chosen[1].get('id','')} | CANDIDATOS {candidates_txt}")

    # Critical collision guard: same source channel cannot feed two different
    # tvg-ids. If it does, only keep the first/highest-priority assignment and
    # mark the other one ambiguous.
    reverse={}
    collision_keys=set()
    for key,item in mappings.items():
        sk=(item["source"],item["source_id"])
        if sk in reverse and reverse[sk] != key:
            collision_keys.add(key)
            warnings.append(
                f"COLISION: {item['source']}:{item['source_id']} -> "
                f"{wanted[reverse[sk]]['id']} y {item['user_id']}; "
                f"se elimina {item['user_id']} por seguridad"
            )
        else:
            reverse[sk]=key

    for key in collision_keys:
        mappings.pop(key,None)

    missing=sorted(
        [info["id"] for key,info in wanted.items() if key not in mappings],
        key=str.casefold
    )

    out=ET.Element("tv",{
        "generator-info-name":"Custom EPG for alvaropah/iptv v9",
        "generator-info-url":"https://github.com/alvaropah/iptv"
    })

    for item in sorted(mappings.values(),key=lambda x:x["user_id"].casefold()):
        c=ET.Element("channel",{"id":item["user_id"]})
        for child in item["channel"]: c.append(child)
        out.append(c)

    seen=set()
    programs=0
    for source_name,root in roots:
        for p in root.findall("programme"):
            sk=(source_name,p.get("channel",""))
            uid=reverse.get(sk)
            if not uid or uid in collision_keys: continue
            channel_id=wanted[uid]["id"]
            k=(channel_id,p.get("start",""),p.get("stop",""),ET.tostring(p,encoding="unicode"))
            if k in seen: continue
            seen.add(k)
            np=ET.Element("programme",dict(p.attrib))
            np.set("channel",channel_id)
            for child in p: np.append(child)
            out.append(np)
            programs+=1

    MISSING.write_text("\n".join(missing)+("\n" if missing else ""),encoding="utf-8")
    MAPPING.write_text(
        "\n".join(
            f'{i["user_id"]} -> {i["source_id"]} | {i["source"]} | exact/alias'
            for i in sorted(mappings.values(),key=lambda x:x["user_id"].casefold())
        )+("\n" if mappings else ""),encoding="utf-8"
    )
    CANDIDATES.write_text(
        "\n".join(candidate_lines)+("\n" if candidate_lines else ""),encoding="utf-8"
    )
    WARNINGS.write_text(
        "\n".join(warnings)+("\n" if warnings else ""),encoding="utf-8"
    )

    ET.indent(out,space="  ")
    ET.ElementTree(out).write(OUT,encoding="utf-8",xml_declaration=True)

    print(f"\nEPG generado: {len(mappings)}/{len(wanted)} canales")
    print(f"Programas: {programs}")
    print(f"Sin EPG: {len(missing)}")
    print(f"Candidatos con varias fuentes: {len(candidate_lines)}")
    print(f"Colisiones bloqueadas: {len(warnings)}")
    print("Archivos: guide.xml, epg_missing.txt, epg_mapping.txt, epg_candidates.txt, epg_duplicate_warnings.txt")

if __name__=="__main__":
    main()
