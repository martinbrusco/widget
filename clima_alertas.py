"""Alertas meteorológicas vía MeteoAlarm (EUMETNET) - feed Atom público y gratuito."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

HEADERS = {"User-Agent": "ClimaWidget/1.0"}

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "cap": "urn:oasis:names:tc:emergency:cap:1.2",
}

# Severidad numérica para ordenar
SEVERIDAD = {
    "minor": 1,
    "moderate": 2,
    "severe": 3,
    "extreme": 4,
}

# Color por severidad (visual)
COLOR_SEVERIDAD = {
    "minor": "#22c55e",
    "moderate": "#eab308",
    "severe": "#f97316",
    "extreme": "#ef4444",
}

EMOJI_TIPO = {
    "thunderstorm": "⛈️",
    "rain": "🌧️",
    "snow": "❄️",
    "wind": "💨",
    "fog": "🌫️",
    "high temperature": "🥵",
    "low temperature": "🥶",
    "coastal event": "🌊",
    "flood": "🌊",
    "forest fire": "🔥",
    "avalanches": "🏔️",
    "ice": "🧊",
    "wave": "🌊",
}

# Traducción del tipo de evento al español. Se busca por substring.
TRADUCCION_EVENTO: list[tuple[str, str]] = [
    ("thunderstorm", "tormentas"),
    ("rain-flood", "lluvias e inundaciones"),
    ("rain", "lluvias"),
    ("snow-ice", "nieve y hielo"),
    ("snow", "nieve"),
    ("wind", "viento"),
    ("fog", "niebla"),
    ("high temperature", "calor extremo"),
    ("low temperature", "frío extremo"),
    ("extreme heat", "calor extremo"),
    ("extreme cold", "frío extremo"),
    ("coastal event", "fenómeno costero"),
    ("flood", "inundaciones"),
    ("forest fire", "incendio forestal"),
    ("fire", "incendio"),
    ("avalanche", "aludes"),
    ("ice", "hielo"),
    ("wave", "oleaje"),
    ("rainfall", "precipitaciones"),
    ("storm", "tormenta"),
]

# Traducción de severidad
TRADUCCION_SEVERIDAD = {
    "minor": "leve",
    "moderate": "moderado",
    "severe": "grave",
    "extreme": "extremo",
    "unknown": "desconocido",
}


def _emoji_evento(evento: str) -> str:
    e = (evento or "").lower()
    for clave, emoji in EMOJI_TIPO.items():
        if clave in e:
            return emoji
    return "⚠️"


def traducir_evento(evento: str) -> str:
    """Devuelve el evento traducido al español. Si no hay traducción, devuelve el original."""
    if not evento:
        return "Aviso meteorológico"
    e = evento.lower().strip()
    # quitar prefijos típicos de MeteoAlarm
    for pref in ("warning of ", "warning ", "alert of ", "alert "):
        if e.startswith(pref):
            e = e[len(pref):].strip()
            break
    # quitar sufijos como " warning"
    for suf in (" warning", " alert", " advisory"):
        if e.endswith(suf):
            e = e[: -len(suf)].strip()
    nivel = ""
    for palabra, etiqueta in (("severe", "grave"), ("extreme", "extremo"), ("moderate", "moderado")):
        if palabra in e:
            nivel = etiqueta
            e = e.replace(palabra, "").strip()
            break
    for substr, traducido in TRADUCCION_EVENTO:
        if substr in e:
            base = f"Aviso de {traducido}"
            return f"{base} ({nivel})" if nivel else base
    # fallback: capitalizar el original
    return f"Aviso: {evento.strip().capitalize()}"


def traducir_severidad(sev: str) -> str:
    return TRADUCCION_SEVERIDAD.get((sev or "").lower(), sev or "")


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    raw = s.replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def traer_alertas_meteo(
    pais: str = "spain", region_filtro: str | None = None
) -> list[dict[str, Any]]:
    """Devuelve avisos vigentes para el país (y región opcional).

    `region_filtro` se compara como substring sobre `areaDesc` (case-insensitive).
    """
    pais = pais.lower().strip()
    url = f"https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-{pais}"
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=10) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except (OSError, URLError, HTTPError, TimeoutError):
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    ahora = datetime.now(timezone.utc)
    avisos: list[dict[str, Any]] = []
    rf = (region_filtro or "").lower().strip() or None
    for entry in root.findall("a:entry", NS):
        info_nodes = entry.findall(".//cap:info", NS)
        if not info_nodes:
            info_nodes = [entry]
        for info in info_nodes:
            severidad_elem = info.find("cap:severity", NS)
            if severidad_elem is None or severidad_elem.text is None:
                continue
            severidad = severidad_elem.text.strip().lower()
            if severidad in ("unknown", "minor"):
                pass
            evento_elem = info.find("cap:event", NS)
            evento = (evento_elem.text or "").strip() if evento_elem is not None else ""
            efectivo = _parse_dt(_text(info, "cap:effective"))
            expira = _parse_dt(_text(info, "cap:expires"))
            if expira is not None and expira < ahora:
                continue
            if efectivo is not None and efectivo > ahora and (
                (efectivo - ahora).total_seconds() > 24 * 3600
            ):
                continue

            descripciones = []
            for area in info.findall("cap:area", NS):
                ad = _text(area, "cap:areaDesc") or ""
                if ad:
                    descripciones.append(ad)
            if not descripciones:
                ad = _text(info, "cap:areaDesc") or _text(entry, "cap:areaDesc") or ""
                if ad:
                    descripciones.append(ad)
            area_desc = ", ".join(descripciones)
            if rf and rf not in area_desc.lower():
                continue
            avisos.append(
                {
                    "evento": evento,
                    "severidad": severidad,
                    "color": COLOR_SEVERIDAD.get(severidad, "#94a3b8"),
                    "emoji": _emoji_evento(evento),
                    "area": area_desc[:80],
                    "desde": efectivo,
                    "hasta": expira,
                    "score": SEVERIDAD.get(severidad, 0),
                }
            )

    # tras la primera pasada, si quedaron muy pocos por la heurística, se devuelve igual
    avisos.sort(key=lambda a: (-a["score"], a["evento"]))
    return avisos


def _text(node: ET.Element, tag: str) -> str | None:
    el = node.find(tag, NS)
    if el is None:
        return None
    return (el.text or "").strip() if el.text else ""


def resumen_alertas(avisos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Devuelve el aviso más severo + total para mostrar en un chip."""
    if not avisos:
        return None
    top = avisos[0]
    return {
        "titulo": traducir_evento(top["evento"] or "Aviso"),
        "severidad": traducir_severidad(top["severidad"]),
        "severidad_raw": top["severidad"],
        "color": top["color"],
        "emoji": top["emoji"],
        "n": len(avisos),
        "area": top.get("area", ""),
    }
