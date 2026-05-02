"""Descarga de audio/video desde YouTube, X/Twitter y más sitios vía yt-dlp."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

try:
    import yt_dlp
except ImportError:
    yt_dlp = None  # type: ignore[assignment]

CALIDADES_VIDEO: list[tuple[str, str]] = [
    ("Mejor disponible", "bv*+ba/b"),
    ("1080p máximo", "bv*[height<=1080]+ba/b"),
    ("720p máximo", "bv*[height<=720]+ba/b"),
    ("480p máximo", "bv*[height<=480]+ba/b"),
    ("360p máximo", "bv*[height<=360]+ba/b"),
]


def ffmpeg_disponible() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def limpiar_mensaje_error(msg: str) -> str:
    """Quita códigos ANSI de errores de yt-dlp (colores en terminal)."""
    s = re.sub(r"\x1b\[[0-9;]*m", "", msg)
    return s.strip()


def yt_dlp_instalado() -> bool:
    return yt_dlp is not None


def es_url_permitida(url: str) -> bool:
    if not url or len(url) > 2048:
        return False
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https"):
        return False
    if not p.netloc:
        return False
    return True


def construir_opciones(
    *,
    url: str,
    solo_audio: bool,
    formato_video: str,
    carpeta: Path,
    progreso: Callable[[str], None],
) -> dict[str, Any]:
    carpeta.mkdir(parents=True, exist_ok=True)
    outtmpl = str(carpeta / "%(title).100B [%(id)s].%(ext)s")

    def hook(d: dict[str, Any]) -> None:
        if d.get("status") == "downloading":
            pct = d.get("_percent_str", "").strip()
            spd = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            nombre = d.get("filename", "") or d.get("info_dict", {}).get("title", "")
            if isinstance(nombre, str) and len(nombre) > 50:
                nombre = nombre[:47] + "…"
            partes = [p for p in (pct, spd, eta) if p]
            msg = " · ".join(partes) if partes else "Descargando…"
            if nombre:
                msg = f"{nombre} — {msg}"
            progreso(msg)
        elif d.get("status") == "finished":
            progreso("Finalizando…")

    tiene_ff = ffmpeg_disponible()
    opts: dict[str, Any] = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
    }

    if solo_audio:
        opts["format"] = "bestaudio/best"
        if tiene_ff:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        # Sin ffmpeg: audio en contenedor nativo (m4a, webm…)
    elif tiene_ff:
        opts["format"] = formato_video
        opts["merge_output_format"] = "mp4"
    else:
        progreso(
            "Sin ffmpeg: usando vídeo en un solo archivo (calidad limitada)…"
        )
        opts["format"] = "best[ext=mp4]/best[height<=1080]/best"

    nota = ""
    if solo_audio and not tiene_ff:
        nota = (
            "Audio en formato original (m4a/webm). Para MP3 instala: "
            "sudo apt install ffmpeg"
        )
    elif (not solo_audio) and (not tiene_ff):
        nota = (
            "Vídeo sin ffmpeg: un solo archivo; el selector de calidad no aplica del todo. "
            "sudo apt install ffmpeg"
        )
    return opts, nota


def ejecutar_descarga(url: str, opciones: dict[str, Any]) -> tuple[bool, str]:
    if not yt_dlp_instalado():
        return False, "yt-dlp no está instalado. Ejecuta de nuevo ./run.sh"
    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:  # type: ignore[union-attr]
            ydl.download([url.strip()])
        return True, "Descarga completada"
    except Exception as e:  # noqa: BLE001
        return False, limpiar_mensaje_error(str(e))[:650]
