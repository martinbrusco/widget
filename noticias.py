"""Titulares de última hora: Infobae (ES) y Fox News (EN → ES)."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ClimaWidget/1.0)"}

URL_INFOBAE_RSS = "https://www.infobae.com/arc/outboundfeeds/rss/"
URL_FOX_RSS = "https://feeds.foxnews.com/foxnews/latest"


def _http_get(url: str, timeout: float = 15.0) -> bytes:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def _texto_elem(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def _extraer_items_rss(xml: bytes, limite: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            if len(out) >= limite:
                break
            tit = _texto_elem(item.find("title"))
            link_el = item.find("link")
            href = (link_el.text or "").strip() if link_el is not None else ""
            if not href:
                guid_el = item.find("guid")
                if guid_el is not None and guid_el.text:
                    href = guid_el.text.strip()
            if tit:
                out.append({"titulo": tit, "url": href or "#"})
        return out
    # Atom (por si Fox u otro cambiara)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        if len(out) >= limite:
            break
        tit = _texto_elem(entry.find("a:title", ns))
        href = ""
        link_el = entry.find("a:link", ns)
        if link_el is not None:
            href = link_el.get("href", "") or ""
        if tit:
            out.append({"titulo": tit, "url": href or "#"})
    return out


def traducir_en_es(texto: str) -> str:
    """Traducción gratuita vía API pública (sin clave)."""
    texto = texto.strip()
    if not texto:
        return texto
    fragmento = texto[:480]
    try:
        url = (
            "https://api.mymemory.translated.net/get?q="
            + quote(fragmento)
            + "&langpair=en|es"
        )
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=12) as r:
            j: dict[str, Any] = json.loads(r.read().decode("utf-8", errors="replace"))
        data = j.get("responseData") or {}
        trad = (data.get("translatedText") or "").strip()
        if trad and trad.lower() != fragmento.lower():
            return trad
    except (OSError, URLError, HTTPError, json.JSONDecodeError, TypeError):
        pass
    try:
        from deep_translator import GoogleTranslator  # type: ignore[import-untyped]

        return str(GoogleTranslator(source="en", target="es").translate(fragmento))
    except Exception:  # noqa: BLE001
        return texto


def obtener_top_noticias(cuántos_por_fuente: int = 2) -> dict[str, Any]:
    """Devuelve {infobae: [{titulo, url}], fox: [{titulo, url}], err: str|None}."""
    err: str | None = None
    infobae: list[dict[str, str]] = []
    fox: list[dict[str, str]] = []
    try:
        raw_ib = _http_get(URL_INFOBAE_RSS)
        infobae = _extraer_items_rss(raw_ib, cuántos_por_fuente)
    except (OSError, URLError, HTTPError, TimeoutError) as e:
        err = f"Infobae: {e}"
    try:
        raw_fx = _http_get(URL_FOX_RSS)
        fox_en = _extraer_items_rss(raw_fx, cuántos_por_fuente)
        fox = []
        for it in fox_en:
            fox.append(
                {
                    "titulo": traducir_en_es(it["titulo"]),
                    "url": it.get("url", "#"),
                }
            )
    except (OSError, URLError, HTTPError, TimeoutError) as e:
        msg = f"Fox News: {e}"
        err = f"{err}; {msg}" if err else msg
    return {"infobae": infobae, "fox": fox, "err": err}
