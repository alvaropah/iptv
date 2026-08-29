#!/usr/bin/env python3
"""
Generador/sincronizador IPTV — diagnóstico + filtrado seguro por tipo.

IMPORTANTE:
- canales.m3u nunca se modifica.
- La clasificación de Series y Películas se obtiene de Xtream API.
- Las categorías se comparan por nombre exacto.
- Las categorías con el mismo nombre pueden existir en SERIES y VOD
  sin mezclarse.
- La primera ejecución imprime un diagnóstico detallado de categorías.
- La playlist final conserva las URLs originales de Xtream, incluidas
  las credenciales necesarias para reproducir el contenido.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.yml"
CHANNELS_FILE = ROOT / "canales.m3u"
OUTPUT_FILE = ROOT / "playlist.m3u"

TIMEOUT = 120
session = requests.Session()
session.headers.update({"User-Agent": "iptv-playlist-generator/3.0"})


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
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    return {
        "series_categories": [
            str(x).strip() for x in (cfg.get("series_categories") or []) if str(x).strip()
        ],
        "movie_categories": [
            str(x).strip() for x in (cfg.get("movie_categories") or []) if str(x).strip()
        ],
    }


def xtream_api(host: str, username: str, password: str, action: str | None = None):
    params = {"username": username, "password": password}
    if action:
        params["action"] = action

    r = session.get(
        f"{host}/player_api.php",
        params=params,
        timeout=TIMEOUT,
    )
    r.raise_for_status()

    try:
        return r.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Xtream devolvió una respuesta que no es JSON para {action or 'login'}."
        ) from exc


def category_names(items) -> list[str]:
    if not isinstance(items, list):
        return []

    return [
        str(x.get("category_name", "")).strip()
        for x in items
        if isinstance(x, dict) and str(x.get("category_name", "")).strip()
    ]


def print_category_diagnostic(config: dict, series_api, movie_api):
    requested_series = config["series_categories"]
    requested_movies = config["movie_categories"]

    available_series = set(category_names(series_api))
    available_movies = set(category_names(movie_api))

    found_series = [x for x in requested_series if x in available_series]
    missing_series = [x for x in requested_series if x not in available_series]

    found_movies = [x for x in requested_movies if x in available_movies]
    missing_movies = [x for x in requested_movies if x not in available_movies]

    print("\n" + "=" * 72)
    print("DIAGNÓSTICO DE CATEGORÍAS XTREAM")
    print("=" * 72)

    print(f"\nSERIES")
    print(f"  Configuradas: {len(requested_series)}")
    print(f"  Encontradas:  {len(found_series)}")
    print(f"  No encontradas: {len(missing_series)}")

    if missing_series:
        print("\n  ❌ SERIES NO ENCONTRADAS:")
        for name in missing_series:
            print(f"     - {name}")

    print(f"\nPELÍCULAS / VOD")
    print(f"  Configuradas: {len(requested_movies)}")
    print(f"  Encontradas:  {len(found_movies)}")
    print(f"  No encontradas: {len(missing_movies)}")

    if missing_movies:
        print("\n  ❌ PELÍCULAS NO ENCONTRADAS:")
        for name in missing_movies:
            print(f"     - {name}")

    # Mostrar categorías del proveedor relacionadas con términos de
    # categorías que no se han encontrado. Sirve para detectar cambios
    # de nomenclatura del proveedor.
    missing_all = missing_series + missing_movies
    candidate_terms = set()

    for name in missing_all:
        # Palabras suficientemente significativas.
        words = re.findall(r"[A-ZÁÉÍÓÚÜÑ0-9+]{4,}", name.upper())
        candidate_terms.update(words)

    candidates = []
    for name in sorted(available_series | available_movies):
        upper = name.upper()
        if any(term in upper for term in candidate_terms):
            candidates.append(name)

    print("\n" + "-" * 72)
    print("CATEGORÍAS DEL PROVEEDOR QUE PUEDEN ESTAR RELACIONADAS")
    print("-" * 72)

    if candidates:
        for name in candidates:
            kinds = []
            if name in available_series:
                kinds.append("SERIES")
            if name in available_movies:
                kinds.append("VOD")
            print(f"  - {name}  [{', '.join(kinds)}]")
    else:
        print("  No se encontraron coincidencias aproximadas.")

    print("\n" + "-" * 72)
    print("CATEGORÍAS DUPLICADAS ENTRE SERIES Y VOD")
    print("-" * 72)

    duplicated = sorted(available_series & available_movies)
    if duplicated:
        for name in duplicated:
            selected_s = name in requested_series
            selected_m = name in requested_movies
            print(
                f"  - {name}"
                f" | configurada SERIES={'SI' if selected_s else 'NO'}"
                f" | configurada VOD={'SI' if selected_m else 'NO'}"
            )
    else:
        print("  No hay categorías con el mismo nombre en ambos tipos.")

    print("=" * 72 + "\n")

    return {
        "available_series": available_series,
        "available_movies": available_movies,
        "missing_series": missing_series,
        "missing_movies": missing_movies,
    }


def read_channels() -> str:
    if not CHANNELS_FILE.exists():
        raise FileNotFoundError("No existe canales.m3u en la raíz del repositorio.")

    text = CHANNELS_FILE.read_text(encoding="utf-8-sig")
    lines = [
        line for line in text.splitlines()
        if line.strip().upper() != "#EXTM3U"
    ]
    return "#EXTM3U\n" + "\n".join(lines).rstrip() + "\n"


def extract_attr(extinf: str, attr: str) -> str | None:
    match = re.search(
        rf'{re.escape(attr)}\s*=\s*(["\'])(.*?)\1',
        extinf,
        flags=re.IGNORECASE,
    )
    return match.group(2) if match else None


def parse_m3u(text: str) -> list[tuple[str, str]]:
    """
    Lee entradas M3U conservando #EXTINF y URL exactamente.
    """
    lines = text.splitlines()
    entries = []
    i = 0

    while i < len(lines):
        if lines[i].lstrip("\ufeff").upper().startswith("#EXTINF"):
            extinf = lines[i]
            j = i + 1

            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines) and not lines[j].startswith("#"):
                entries.append((extinf, lines[j]))
                i = j + 1
                continue

        i += 1

    return entries


def download_xtream_m3u(host: str, username: str, password: str) -> str:
    print("Descargando M3U de Xtream...")

    r = session.get(
        f"{host}/get.php",
        params={
            "username": username,
            "password": password,
            "type": "m3u_plus",
            "output": "ts",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()

    content = r.content.decode("utf-8-sig", errors="replace")

    if "#EXTM3U" not in content[:5000].upper():
        raise RuntimeError(
            "La respuesta de Xtream no parece una M3U válida."
        )

    print(f"M3U descargada: {len(content) / 1024 / 1024:.2f} MiB")
    return content


def normalize_category(value: str | None) -> str:
    return (value or "").strip()


def classify_entry(extinf: str, url: str) -> str:
    """
    Clasificación de respaldo basada en la URL.

    En Xtream, normalmente:
      /series/  -> SERIES
      /movie/   -> VOD

    Se usa SOLO para separar tipos; la categoría sigue siendo
    comprobada contra las listas de categorías de Xtream.
    """
    path = url.lower()

    if "/series/" in path:
        return "series"
    if "/movie/" in path:
        return "movie"

    # Algunos proveedores pueden usar otros patrones. No asumimos.
    return "unknown"


def filter_by_api_categories(
    entries: list[tuple[str, str]],
    requested_series: set[str],
    requested_movies: set[str],
    available_series: set[str],
    available_movies: set[str],
):
    """
    Filtra de forma segura:
      1. Detecta si la URL es /series/ o /movie/.
      2. Solo permite la categoría si pertenece al conjunto correspondiente.

    Esto resuelve el caso de categorías con el mismo nombre en Series y VOD.
    """
    selected = []
    counts_series: dict[str, int] = {}
    counts_movies: dict[str, int] = {}

    for extinf, url in entries:
        group = normalize_category(extract_attr(extinf, "group-title"))
        if not group:
            continue

        kind = classify_entry(extinf, url)

        if kind == "series":
            if group in requested_series and group in available_series:
                selected.append((extinf, url))
                counts_series[group] = counts_series.get(group, 0) + 1

        elif kind == "movie":
            if group in requested_movies and group in available_movies:
                selected.append((extinf, url))
                counts_movies[group] = counts_movies.get(group, 0) + 1

    return selected, counts_series, counts_movies


def print_counts(title: str, counts: dict[str, int], requested: list[str]):
    print(f"\n{title}")
    total = 0

    for name in requested:
        count = counts.get(name, 0)
        total += count
        marker = "✅" if count else "⚠️"
        print(f"  {marker} {name}: {count:,}")

    print(f"  TOTAL: {total:,}")


def entries_to_text(entries: list[tuple[str, str]]) -> str:
    lines = []
    for extinf, url in entries:
        lines.extend([extinf, url])
    return "\n".join(lines)


def main():
    host = normalize_host(required_env("XTREAM_HOST"))
    username = required_env("XTREAM_USERNAME")
    password = required_env("XTREAM_PASSWORD")

    config = load_config()

    print("Autenticando contra Xtream API...")
    auth = xtream_api(host, username, password)

    if not isinstance(auth, dict):
        raise RuntimeError("Respuesta inesperada de Xtream al autenticar.")

    user_info = auth.get("user_info", {})
    if isinstance(user_info, dict) and str(user_info.get("auth", "1")) == "0":
        raise RuntimeError("Xtream ha rechazado las credenciales.")

    print("Autenticación correcta.")

    print("Consultando categorías reales de Xtream...")
    series_api = xtream_api(host, username, password, "get_series_categories")
    movie_api = xtream_api(host, username, password, "get_vod_categories")

    diagnostic = print_category_diagnostic(config, series_api, movie_api)

    print("Leyendo canales.m3u...")
    channels = read_channels()

    source = download_xtream_m3u(host, username, password)
    entries = parse_m3u(source)

    print(f"Entradas totales en Xtream: {len(entries):,}")

    selected, series_counts, movie_counts = filter_by_api_categories(
        entries,
        set(config["series_categories"]),
        set(config["movie_categories"]),
        diagnostic["available_series"],
        diagnostic["available_movies"],
    )

    print_counts(
        "ENTRADAS POR CATEGORÍA — SERIES",
        series_counts,
        config["series_categories"],
    )

    print_counts(
        "ENTRADAS POR CATEGORÍA — PELÍCULAS/VOD",
        movie_counts,
        config["movie_categories"],
    )

    series_total = sum(series_counts.values())
    movie_total = sum(movie_counts.values())

    print(f"\nEntradas seleccionadas: {len(selected):,}")
    print(f"Entradas de series: {series_total:,}")
    print(f"Entradas de películas: {movie_total:,}")

    # Canales primero, contenido Xtream después.
    generated = entries_to_text(selected)

    if generated:
        final_text = channels.rstrip() + "\n" + generated.rstrip() + "\n"
    else:
        final_text = channels

    OUTPUT_FILE.write_text(final_text, encoding="utf-8")

    print("\nPlaylist generada correctamente.")
    print(f"Archivo: {OUTPUT_FILE.name}")
    print(f"Tamaño final: {OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MiB")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
