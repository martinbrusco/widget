"""Autostart: Linux (XDG ~/.config/autostart) y Windows (carpeta Inicio del usuario)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

NOMBRE_ENTRADA = "clima-widget"
NOMBRE_BAT_STARTUP = "ClimaWidget-autostart.bat"


def es_windows() -> bool:
    return sys.platform == "win32"


def _carpeta_autostart_linux() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart"


def _ruta_desktop_linux() -> Path:
    return _carpeta_autostart_linux() / f"{NOMBRE_ENTRADA}.desktop"


def _carpeta_startup_windows() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _ruta_bat_startup_windows() -> Path | None:
    carpeta = _carpeta_startup_windows()
    if carpeta is None:
        return None
    return carpeta / NOMBRE_BAT_STARTUP


def autostart_activo() -> bool:
    if es_windows():
        p = _ruta_bat_startup_windows()
        return bool(p and p.exists())
    p = _ruta_desktop_linux()
    if not p.exists():
        return False
    try:
        contenido = p.read_text(encoding="utf-8")
    except OSError:
        return False
    if "Hidden=true" in contenido:
        return False
    if "X-GNOME-Autostart-enabled=false" in contenido:
        return False
    return True


def activar(ruta_lanzador: str | os.PathLike[str]) -> tuple[bool, str]:
    lanzador = Path(ruta_lanzador).resolve()
    if not lanzador.exists():
        return False, f"No existe el lanzador: {lanzador}"

    if es_windows():
        dest_bat = _ruta_bat_startup_windows()
        if dest_bat is None:
            return False, "No se encontró APPDATA (variable de entorno)."
        try:
            contenido = (
                "@echo off\r\n"
                f'cd /d "{lanzador.parent}"\r\n'
                f'call "{lanzador}"\r\n'
            )
            dest_bat.parent.mkdir(parents=True, exist_ok=True)
            dest_bat.write_text(contenido, encoding="utf-8")
        except OSError as exc:
            return False, str(exc)
        return True, str(dest_bat)

    cmd = f"bash -lc {_quote(str(lanzador))}"
    contenido = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Clima · Sistema · Deportes\n"
        "Comment=Widget de clima, métricas del sistema y deportes\n"
        f"Exec={cmd}\n"
        f"Path={_quote(str(lanzador.parent))}\n"
        "Icon=weather-clear\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-KDE-autostart-after=panel\n"
        "Hidden=false\n"
    )
    try:
        carpeta = _carpeta_autostart_linux()
        carpeta.mkdir(parents=True, exist_ok=True)
        _ruta_desktop_linux().write_text(contenido, encoding="utf-8")
    except OSError as exc:
        return False, f"No se pudo escribir: {exc}"
    return True, str(_ruta_desktop_linux())


def desactivar() -> tuple[bool, str]:
    if es_windows():
        p = _ruta_bat_startup_windows()
        if not p or not p.exists():
            return True, "Ya estaba desactivado"
        try:
            p.unlink()
        except OSError as exc:
            return False, str(exc)
        return True, "Eliminado del Inicio"
    p = _ruta_desktop_linux()
    if not p.exists():
        return True, "Ya estaba desactivado"
    try:
        p.unlink()
    except OSError as exc:
        return False, f"No se pudo borrar: {exc}"
    return True, "Eliminado"


def _quote(s: str) -> str:
    if not s:
        return '""'
    if any(c in s for c in (' ', '\t', '"', "'", '$', '\\')):
        escaped = s.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    return s


def ruta_lanzador_por_defecto(base_proyecto: Path) -> Path:
    """run.bat en Windows, run.sh en Linux/macOS."""
    if es_windows():
        return base_proyecto / "run.bat"
    return base_proyecto / "run.sh"
