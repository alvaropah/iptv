#!/usr/bin/env python3
"""
Genera playlist.m3u conservando canales.m3u al principio y añadiendo
películas/series seleccionadas desde una cuenta Xtream Codes.

Requiere variables de entorno:
  XTREAM_HOST
  XTREAM_USERNAME
  XTREAM_PASSWORD

Requiere:
  pip install requests pyyaml
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests
import yaml

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.yml"
CHANNELS_FILE = ROOT / "canales.m3u"
OUTPUT_FILE = ROOT / "playlist.m3u"

TIMEOUT = 60
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "iptv-playlist-generator/1.0"})


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta el GitHub Secret/variable de entorno: {name}")
    return value


def api_get(host: str, username: str, password: str, action: str, **extra):
    params = {
        "username": username,
        "password": password,
        "action": action,
        **extra,
    }
    r = SESSION.get(f"{host}/player_api.php", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    # Algunas implementaciones devuelven un objeto con auth cuando falla.
    if isinstance(data, dict) and "user_info" in data:
        auth = data["user_info"].get("auth")
        if str(auth) == "0":
            raise RuntimeError("Xtream ha rechazado las credenciales.")
    return data


def clean_attr(value) -> str:
    return str(value or "").replace('"', "'").replace("\r", " ").replace("\n", " ").strip()


def category_map(items):
    return {
        clean_attr(x.get("category_name")): str(x.get("category_id"))
        for x in items
        if x.get("category_name") is not None and x.get("category_id") is not None
    }


def quote_path_part(value: str) -> str:
    return quote(str(value), safe="")


def series_episode_url(host, username, password, episode):
    ext = clean_attr(episode.get("container_extension")) or "mkv"
    stream_id = episode.get("id")
    return (
        f"{host}/series/{quote_path_part(username)}/{quote_path_part(password)}/"
        f"{stream_id}.{quote_path_part(ext)}"
    )


def movie_url(host, username, password, movie):
    ext = clean_attr(movie.get("container_extension")) or "mkv"
    stream_id = movie.get("stream_id")
    return (
        f"{host}/movie/{quote_path_part(username)}/{quote_path_part(password)}/"
        f"{stream_id}.{quote_path_part(ext)}"
    )


def load_config():
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return {
        "series_categories": cfg.get("series_categories") or [],
        "movie_categories": cfg.get("movie_categories") or [],
    }


def read_channels():
    if not CHANNELS_FILE.exists():
        raise FileNotFoundError(
            "No existe canales.m3u en la raíz del repositorio."
        )
    text = CHANNELS_FILE.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    # Conservamos la lista exactamente, salvo cabeceras #EXTM3U duplicadas.
    body = [line for line in lines if line.strip().upper() != "#EXTM3U"]
    return "#EXTM3U\n" + "\n".join(body).rstrip() + "\n"


def build_series(host, username, password, selected_names, series_categories):
    wanted = set(selected_names)
    by_name = category_map(series_categories)

    missing = sorted(wanted - set(by_name))
    if missing:
        print("AVISO: categorías de series no encontradas:")
        for name in missing:
            print(f"  - {name}")

    result = []
    total_series = 0
    total_episodes = 0

    for category_name in selected_names:
        category_id = by_name.get(category_name)
        if category_id is None:
            continue

        series_list = api_get(
            host, username, password, "get_series", category_id=category_id
        )
        if not isinstance(series_list, list):
            continue

        for series in series_list:
            total_series += 1
            series_id = series.get("series_id")
            series_name = clean_attr(series.get("name"))
            logo = clean_attr(series.get("cover") or series.get("stream_icon"))

            if not series_id:
                continue

            info = api_get(
                host, username, password, "get_series_info", series_id=series_id
            )
            episodes_by_season = (info or {}).get("episodes", {}) if isinstance(info, dict) else {}

            # Ordenamos temporadas y episodios numéricamente.
            for season_key in sorted(
                episodes_by_season,
                key=lambda x: int(x) if str(x).isdigit() else str(x),
            ):
                episodes = episodes_by_season.get(season_key) or []
                episodes = sorted(
                    episodes,
                    key=lambda e: (
                        int(e.get("episode_num", 0) or 0),
                        clean_attr(e.get("title")).lower(),
                    ),
                )

                try:
                    season_num = int(season_key)
                except (TypeError, ValueError):
                    season_num = 0

                for ep in episodes:
                    ep_num = ep.get("episode_num", "")
                    ep_title = clean_attr(ep.get("title")) or f"Episodio {ep_num}"
                    display = f"{series_name} S{season_num:02d}E{int(ep_num):02d} - {ep_title}" if str(ep_num).isdigit() else f"{series_name} - {ep_title}"

                    attrs = [
                        'tvg-name="' + clean_attr(display) + '"',
                        'tvg-logo="' + logo + '"',
                        'group-title="' + category_name + '"',
                    ]
                    result.append("#EXTINF:-1 " + " ".join(attrs) + "," + display)
                    result.append(series_episode_url(host, username, password, ep))
                    total_episodes += 1

    print(f"Series encontradas: {total_series}")
    print(f"Episodios generados: {total_episodes}")
    return result


def build_movies(host, username, password, selected_names, movie_categories):
    wanted = set(selected_names)
    by_name = category_map(movie_categories)

    missing = sorted(wanted - set(by_name))
    if missing:
        print("AVISO: categorías de películas no encontradas:")
        for name in missing:
            print(f"  - {name}")

    result = []
    total_movies = 0

    for category_name in selected_names:
        category_id = by_name.get(category_name)
        if category_id is None:
            continue

        movies = api_get(
            host, username, password, "get_vod_streams", category_id=category_id
        )
        if not isinstance(movies, list):
            continue

        for movie in movies:
            name = clean_attr(movie.get("name"))
            logo = clean_attr(movie.get("stream_icon"))
            if not name or movie.get("stream_id") is None:
                continue

            attrs = [
                'tvg-name="' + name + '"',
                'tvg-logo="' + logo + '"',
                'group-title="' + category_name + '"',
            ]
            result.append("#EXTINF:-1 " + " ".join(attrs) + "," + name)
            result.append(movie_url(host, username, password, movie))
            total_movies += 1

    print(f"Películas generadas: {total_movies}")
    return result


def main():
    host = required_env("XTREAM_HOST").rstrip("/")
    username = required_env("XTREAM_USERNAME")
    password = required_env("XTREAM_PASSWORD")
    cfg = load_config()

    # Verificación de autenticación.
    account = api_get(host, username, password, "")
    if not isinstance(account, dict):
        raise RuntimeError("Respuesta inesperada de Xtream.")

    series_categories = api_get(host, username, password, "get_series_categories")
    movie_categories = api_get(host, username, password, "get_vod_categories")

    if not isinstance(series_categories, list):
        raise RuntimeError("Xtream no devolvió una lista válida de categorías de series.")
    if not isinstance(movie_categories, list):
        raise RuntimeError("Xtream no devolvió una lista válida de categorías VOD.")

    channels = read_channels()

    generated = []
    generated.append("")
    generated.append("# ===== SERIES GENERADAS AUTOMÁTICAMENTE =====")
    generated.extend(
        build_series(
            host,
            username,
            password,
            cfg["series_categories"],
            series_categories,
        )
    )
    generated.append("")
    generated.append("# ===== PELÍCULAS GENERADAS AUTOMÁTICAMENTE =====")
    generated.extend(
        build_movies(
            host,
            username,
            password,
            cfg["movie_categories"],
            movie_categories,
        )
    )

    final_text = channels.rstrip() + "\n" + "\n".join(generated).rstrip() + "\n"
    OUTPUT_FILE.write_text(final_text, encoding="utf-8")

    print(f"Playlist generada: {OUTPUT_FILE}")
    print(f"Tamaño: {OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MiB")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
