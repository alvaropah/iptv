#!/usr/bin/env python3
"""
Generador/sincronizador IPTV v4.

- canales.m3u se conserva íntegramente y siempre va primero.
- Series y películas se filtran desde la M3U de Xtream.
- Series/VOD se separan por el tipo de URL (/series/ y /movie/).
- Las categorías VOD se colocan EXACTAMENTE en el orden de config.yml.
- Dentro de cada categoría se conserva el orden entregado por Xtream.
- El diagnóstico detallado puede activarse con DIAGNOSTIC_MODE=true.
- En modo normal no hace el diagnóstico completo.
- No usa get_series_info por cada serie: solo descarga la M3U una vez
  y consulta las categorías de la API.
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
session.headers.update({"User-Agent": "iptv-playlist-generator/4.0"})


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
        "series_categories": [
            str(x).strip()
            for x in (cfg.get("series_categories") or [])
            if str(x).strip()
        ],
        "movie_categories": [
            str(x).strip()
            for x in (cfg.get("movie_categories") or [])
            if str(x).strip()
        ],
    }


def xtream_api(host: str, username: str, password: str, action: str | None = None):
    params = {
        "username": username,
        "password": password,
    }

    if action:
        params["action"] = action

    response = session.get(
        f"{host}/player_api.php",
        params=params,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Xtream no devolvió JSON válido para {action or 'login'}."
        ) from exc


def category_names(items) -> set[str]:
    if not isinstance(items, list):
        return set()

    return {
        str(item.get("category_name", "")).strip()
        for item in items
        if isinstance(item, dict)
        and str(item.get("category_name", "")).strip()
    }


def run_diagnostic(config: dict, series_api, movie_api):
    """
    Diagnóstico opcional. Se ejecuta solo si DIAGNOSTIC_MODE=true.
    """
    requested_series = config["series_categories"]
    requested_movies = config["movie_categories"]

    available_series = category_names(series_api)
    available_movies = category_names(movie_api)

    found_series = [x for x in requested_series if x in available_series]
    missing_series = [x for x in requested_series if x not in available_series]

    found_movies = [x for x in requested_movies if x in available_movies]
    missing_movies = [x for x in requested_movies if x not in available_movies]

    print("\n" + "=" * 72)
    print("DIAGNÓSTICO DE CATEGORÍAS XTREAM")
    print("=" * 72)

    print("\nSERIES")
    print(f"  Configuradas: {len(requested_series)}")
    print(f"  Encontradas:  {len(found_series)}")
    print(f"  No encontradas: {len(missing_series)}")

    if missing_series:
        print("\n  ❌ SERIES NO ENCONTRADAS:")
        for name in missing_series:
            print(f"     - {name}")

    print("\nPELÍCULAS / VOD")
    print(f"  Configuradas: {len(requested_movies)}")
    print(f"  Encontradas:  {len(found_movies)}")
    print(f"  No encontradas: {len(missing_movies)}")

    if missing_movies:
        print("\n  ❌ PELÍCULAS NO ENCONTRADAS:")
        for name in missing_movies:
            print(f"     - {name}")

    print("\n" + "-" * 72)
    print("CATEGORÍAS DUPLICADAS ENTRE SERIES Y VOD")
    print("-" * 72)

    duplicated = sorted(available_series & available_movies)

    if duplicated:
        for name in duplicated:
            print(
                f"  - {name}"
                f" | configurada SERIES={'SI' if name in requested_series else 'NO'}"
                f" | configurada VOD={'SI' if name in requested_movies else 'NO'}"
            )
    else:
        print("  No hay categorías con el mismo nombre en ambos tipos.")

    print("=" * 72 + "\n")


def read_channels() -> str:
    if not CHANNELS_FILE.exists():
        raise FileNotFoundError(
            "No existe canales.m3u en la raíz del repositorio."
        )

    text = CHANNELS_FILE.read_text(encoding="utf-8-sig")

    # Quitamos únicamente posibles #EXTM3U duplicados.
    lines = [
        line
        for line in text.splitlines()
        if line.strip().upper() != "#EXTM3U"
    ]

    return "#EXTM3U\n" + "\n".join(lines).rstrip() + "\n"


def extract_attr(extinf: str, attr: str) -> str | None:
    match = re.search(
        rf'{re.escape(attr)}\s*=\s*(["\'])(.*?)\1',
        extinf,
        flags=re.IGNORECASE,
    )

    return match.group(2).strip() if match else None


def parse_m3u(text: str) -> list[tuple[str, str]]:
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

    response = session.get(
        f"{host}/get.php",
        params={
            "username": username,
            "password": password,
            "type": "m3u_plus",
            "output": "ts",
        },
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    content = response.content.decode("utf-8-sig", errors="replace")

    if "#EXTM3U" not in content[:5000].upper():
        raise RuntimeError(
            "La respuesta de Xtream no parece una M3U válida."
        )

    print(f"M3U descargada: {len(content) / 1024 / 1024:.2f} MiB")

    return content


def classify_entry(url: str) -> str:
    """
    Xtream normalmente utiliza:
      /series/ -> Series
      /movie/  -> VOD
    """
    lower_url = url.lower()

    if "/series/" in lower_url:
        return "series"

    if "/movie/" in lower_url:
        return "movie"

    return "unknown"


def filter_and_order(
    entries: list[tuple[str, str]],
    series_categories: list[str],
    movie_categories: list[str],
):
    """
    Construye dos mapas de listas.

    La clave es la categoría exacta y el valor conserva el orden original
    de Xtream.

    Después se reconstruyen siguiendo el orden de config.yml.
    """

    wanted_series = set(series_categories)
    wanted_movies = set(movie_categories)

    series_by_category: dict[str, list[tuple[str, str]]] = {
        category: [] for category in series_categories
    }

    movies_by_category: dict[str, list[tuple[str, str]]] = {
        category: [] for category in movie_categories
    }

    for extinf, url in entries:
        category = extract_attr(extinf, "group-title")

        if not category:
            continue

        kind = classify_entry(url)

        if kind == "series" and category in wanted_series:
            series_by_category[category].append((extinf, url))

        elif kind == "movie" and category in wanted_movies:
            movies_by_category[category].append((extinf, url))

    ordered = []

    # SERIES: categorías exactamente en el orden de config.yml.
    # Dentro de cada categoría: orden alfabético por título.
    for category in series_categories:
        ordered.extend(
            sort_entries_alphabetically(series_by_category[category])
        )

    # PELÍCULAS/VOD: categorías exactamente en el orden de config.yml.
    # Dentro de cada categoría: orden alfabético por título.
    for category in movie_categories:
        ordered.extend(
            sort_entries_alphabetically(movies_by_category[category])
        )

    return ordered, series_by_category, movies_by_category


def entry_display_name(extinf: str) -> str:
    """
    Extrae el título visible de #EXTINF.

    En una línea M3U típica:
      #EXTINF:-1 tvg-id="..." group-title="...",Título

    El nombre que queremos ordenar es lo que aparece después de la última
    coma. No usamos tvg-name ni group-title porque pueden no coincidir con
    el título que muestra el reproductor.
    """
    if "," in extinf:
        return extinf.rsplit(",", 1)[1].strip()

    return extinf.strip()


def sort_entries_alphabetically(
    entries: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """
    Orden alfabético por título visible, sin distinguir mayúsculas/minúsculas.

    casefold() proporciona una comparación Unicode más robusta que lower(),
    especialmente para títulos con caracteres internacionales.
    """
    return sorted(
        entries,
        key=lambda item: entry_display_name(item[0]).casefold(),
    )


def entries_to_text(entries: list[tuple[str, str]]) -> str:
    lines = []

    for extinf, url in entries:
        lines.append(extinf)
        lines.append(url)

    return "\n".join(lines)


def print_summary(
    series_categories: list[str],
    movie_categories: list[str],
    series_by_category: dict[str, list],
    movies_by_category: dict[str, list],
):
    print("\nRESUMEN DE CONTENIDO SELECCIONADO")
    print("-" * 72)

    print("\nSERIES:")
    series_total = 0

    for category in series_categories:
        count = len(series_by_category[category])
        series_total += count
        print(f"  {category}: {count:,}")

    print(f"  TOTAL SERIES: {series_total:,}")

    print("\nPELÍCULAS / VOD:")
    movie_total = 0

    for category in movie_categories:
        count = len(movies_by_category[category])
        movie_total += count
        print(f"  {category}: {count:,}")

    print(f"  TOTAL PELÍCULAS: {movie_total:,}")
    print(f"\nTOTAL CONTENIDO VOD: {series_total + movie_total:,}")


def main():
    host = normalize_host(required_env("XTREAM_HOST"))
    username = required_env("XTREAM_USERNAME")
    password = required_env("XTREAM_PASSWORD")

    config = load_config()

    series_categories = config["series_categories"]
    movie_categories = config["movie_categories"]

    print(f"Categorías de series configuradas: {len(series_categories)}")
    print(f"Categorías de películas configuradas: {len(movie_categories)}")

    print("\nAutenticando contra Xtream API...")
    auth = xtream_api(host, username, password)

    if not isinstance(auth, dict):
        raise RuntimeError("Respuesta inesperada de Xtream al autenticar.")

    user_info = auth.get("user_info", {})

    if (
        isinstance(user_info, dict)
        and str(user_info.get("auth", "1")) == "0"
    ):
        raise RuntimeError("Xtream ha rechazado las credenciales.")

    print("Autenticación correcta.")

    print("Consultando categorías reales de Xtream...")
    series_api = xtream_api(
        host,
        username,
        password,
        "get_series_categories",
    )

    movie_api = xtream_api(
        host,
        username,
        password,
        "get_vod_categories",
    )

    available_series = category_names(series_api)
    available_movies = category_names(movie_api)

    # En modo normal no imprimimos el diagnóstico completo, pero sí
    # comprobamos las categorías. Esto evita generar una playlist vacía
    # por un cambio accidental de configuración.
    missing_series = [
        x for x in series_categories if x not in available_series
    ]
    missing_movies = [
        x for x in movie_categories if x not in available_movies
    ]

    diagnostic_mode = (
        os.environ.get("DIAGNOSTIC_MODE", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )

    if diagnostic_mode:
        run_diagnostic(config, series_api, movie_api)

    if missing_series:
        print(
            f"AVISO: {len(missing_series)} categorías de series "
            "no aparecen en la API."
        )
        for name in missing_series:
            print(f"  - {name}")

    if missing_movies:
        print(
            f"AVISO: {len(missing_movies)} categorías VOD "
            "no aparecen en la API."
        )
        for name in missing_movies:
            print(f"  - {name}")

    print("\nLeyendo canales.m3u...")
    channels = read_channels()

    source = download_xtream_m3u(host, username, password)
    entries = parse_m3u(source)

    if not entries:
        raise RuntimeError(
            "No se encontraron entradas #EXTINF en la M3U de Xtream."
        )

    print(f"Entradas totales en Xtream: {len(entries):,}")

    ordered, series_by_category, movies_by_category = filter_and_order(
        entries,
        series_categories,
        movie_categories,
    )

    print_summary(
        series_categories,
        movie_categories,
        series_by_category,
        movies_by_category,
    )

    print(f"\nEntradas seleccionadas: {len(ordered):,}")

    generated = entries_to_text(ordered)

    if generated:
        final_text = (
            channels.rstrip()
            + "\n"
            + generated.rstrip()
            + "\n"
        )
    else:
        final_text = channels

    OUTPUT_FILE.write_text(
        final_text,
        encoding="utf-8",
    )

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
