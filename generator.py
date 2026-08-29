#!/usr/bin/env python3
"""
Generador/sincronizador de playlist IPTV.

Objetivo:
- Conserva canales.m3u como lista maestra y no lo modifica.
- Descarga la M3U completa de Xtream.
- Filtra únicamente las categorías definidas en config.yml.
- Añade ese contenido después de los canales.
- Mantiene una lista final M3U limpia, sin separadores artificiales.
- Usa los GitHub Secrets XTREAM_HOST, XTREAM_USERNAME y XTREAM_PASSWORD.
- En cada ejecución reconstruye la parte automática a partir de la fuente actual.
  Esto evita duplicados y elimina contenido que el proveedor haya retirado.

La parte de canales siempre procede de canales.m3u.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.yml"
CHANNELS_FILE = ROOT / "canales.m3u"
OUTPUT_FILE = ROOT / "playlist.m3u"

TIMEOUT = 120
MAX_REDIRECTS = 5


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta el GitHub Secret: {name}")
    return value


def normalize_host(host: str) -> str:
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "https://" + host
    return host


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("No existe config.yml.")

    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    return {
        "series_categories": cfg.get("series_categories") or [],
        "movie_categories": cfg.get("movie_categories") or [],
    }


def read_channels() -> str:
    if not CHANNELS_FILE.exists():
        raise FileNotFoundError("No existe canales.m3u en la raíz del repositorio.")

    text = CHANNELS_FILE.read_text(encoding="utf-8-sig")

    # Eliminamos únicamente posibles cabeceras #EXTM3U para añadir una sola.
    lines = [
        line for line in text.splitlines()
        if line.strip().upper() != "#EXTM3U"
    ]

    return "#EXTM3U\n" + "\n".join(lines).rstrip() + "\n"


def extract_group_title(extinf: str) -> str | None:
    """
    Obtiene group-title="..." de una línea #EXTINF.
    Admite comillas simples o dobles y caracteres Unicode.
    """
    match = re.search(
        r'group-title\s*=\s*(["\'])(.*?)\1',
        extinf,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(2)


def parse_m3u(text: str) -> list[tuple[str, str]]:
    """
    Devuelve pares (#EXTINF, URL) conservando exactamente las líneas.
    Solo procesa entradas M3U completas.
    """
    lines = text.splitlines()
    entries = []

    i = 0
    while i < len(lines):
        line = lines[i].strip("\ufeff")

        if line.upper().startswith("#EXTINF"):
            extinf = lines[i]
            j = i + 1

            # Una entrada M3U normalmente tiene la URL inmediatamente después.
            # Saltamos líneas vacías, pero no eliminamos metadatos.
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines) and not lines[j].startswith("#"):
                entries.append((extinf, lines[j]))
                i = j + 1
                continue

        i += 1

    return entries


def download_xtream_m3u(host: str, username: str, password: str) -> str:
    """
    Descarga la M3U del proveedor directamente.
    No guardamos la URL con credenciales en el repositorio.
    """
    url = f"{host}/get.php"

    params = {
        "username": username,
        "password": password,
        "type": "m3u_plus",
        "output": "ts",
    }

    print("Descargando M3U de Xtream...")

    response = requests.get(
        url,
        params=params,
        timeout=TIMEOUT,
        allow_redirects=True,
        headers={"User-Agent": "iptv-playlist-generator/2.0"},
    )
    response.raise_for_status()

    content = response.content.decode("utf-8-sig", errors="replace")

    if "#EXTM3U" not in content[:5000].upper():
        preview = content[:300].replace("\n", " ")
        raise RuntimeError(
            "La respuesta del proveedor no parece ser una M3U válida. "
            f"Respuesta inicial: {preview}"
        )

    print(
        f"M3U descargada: {len(content) / 1024 / 1024:.2f} MiB"
    )

    return content


def selected_categories(config: dict) -> tuple[set[str], set[str]]:
    series = {
        str(x).strip()
        for x in config["series_categories"]
        if str(x).strip()
    }
    movies = {
        str(x).strip()
        for x in config["movie_categories"]
        if str(x).strip()
    }
    return series, movies


def filter_entries(
    entries: list[tuple[str, str]],
    wanted_categories: set[str],
) -> tuple[list[tuple[str, str]], dict[str, int], int]:
    """
    Filtra por group-title exacto.

    Importante:
    NO modifica las URLs ni los #EXTINF.
    Por tanto, si Xtream proporciona URLs con usuario/contraseña,
    esas URLs se conservan tal cual en la playlist final.
    """
    selected = []
    counts: dict[str, int] = {}
    missing_candidates = set()

    for extinf, url in entries:
        group = extract_group_title(extinf)

        if group is None:
            continue

        if group in wanted_categories:
            selected.append((extinf, url))
            counts[group] = counts.get(group, 0) + 1

    return selected, counts, len(selected)


def entries_to_text(entries: list[tuple[str, str]]) -> str:
    if not entries:
        return ""

    lines = []
    for extinf, url in entries:
        lines.append(extinf)
        lines.append(url)

    return "\n".join(lines)


def main() -> None:
    host = normalize_host(required_env("XTREAM_HOST"))
    username = required_env("XTREAM_USERNAME")
    password = required_env("XTREAM_PASSWORD")

    config = load_config()
    series_categories, movie_categories = selected_categories(config)
    wanted_categories = series_categories | movie_categories

    if not wanted_categories:
        raise RuntimeError(
            "No hay ninguna categoría seleccionada en config.yml."
        )

    print(f"Categorías de series configuradas: {len(series_categories)}")
    print(f"Categorías de películas configuradas: {len(movie_categories)}")
    print(f"Categorías totales a filtrar: {len(wanted_categories)}")

    channels_text = read_channels()
    source_m3u = download_xtream_m3u(host, username, password)
    source_entries = parse_m3u(source_m3u)

    if not source_entries:
        raise RuntimeError("No se encontraron entradas #EXTINF en la M3U de Xtream.")

    print(f"Entradas totales en Xtream: {len(source_entries):,}")

    selected, counts, selected_total = filter_entries(
        source_entries,
        wanted_categories,
    )

    # Diagnóstico: categorías configuradas que no aparecen en la M3U.
    found_categories = set(counts)
    missing = sorted(wanted_categories - found_categories)

    if missing:
        print("\nAVISO: estas categorías configuradas no aparecen en la M3U:")
        for category in missing:
            print(f"  - {category}")

    print(f"\nEntradas seleccionadas: {selected_total:,}")

    # Separa estadísticas sin alterar el orden original de Xtream.
    series_total = 0
    movie_total = 0

    for extinf, _ in selected:
        group = extract_group_title(extinf)
        if group in series_categories:
            series_total += 1
        elif group in movie_categories:
            movie_total += 1

    print(f"Entradas de series: {series_total:,}")
    print(f"Entradas de películas: {movie_total:,}")

    # Conservamos el orden de canales.m3u y después el orden que entrega Xtream.
    generated_text = entries_to_text(selected)

    if generated_text:
        final_text = channels_text.rstrip() + "\n" + generated_text.rstrip() + "\n"
    else:
        final_text = channels_text

    OUTPUT_FILE.write_text(final_text, encoding="utf-8")

    size_mib = OUTPUT_FILE.stat().st_size / 1024 / 1024

    print("\nPlaylist generada correctamente.")
    print(f"Archivo: {OUTPUT_FILE.name}")
    print(f"Tamaño final: {size_mib:.2f} MiB")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
