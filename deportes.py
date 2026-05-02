"""Deportes con APIs gratuitas y sin clave.

Fuentes:
- TheSportsDB (clave de pruebas pública "3"): La Liga, Champions, Bundesliga,
  Premier, NBA, MLB. Se usa `eventsseason.php` para descubrir los IDs reales
  de los equipos (los demás endpoints están limitados con la clave gratuita).
- Jolpica-F1 (sucesor de Ergast): calendario y resultados de Fórmula 1.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

HEADERS = {"User-Agent": "ClimaWidget/1.0"}

TSD_BASE = "https://www.thesportsdb.com/api/v1/json/3"
JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"

LIGAS_TSD: dict[str, dict[str, Any]] = {
    "laliga": {
        "id_liga": 4335,
        "nombre": "La Liga",
        "deporte": "futbol",
        "emoji": "⚽",
        "temporada_anyo_dual": True,
    },
    "champions": {
        "id_liga": 4480,
        "nombre": "Champions League",
        "deporte": "futbol",
        "emoji": "⚽",
        "temporada_anyo_dual": True,
    },
    "bundesliga": {
        "id_liga": 4331,
        "nombre": "Bundesliga",
        "deporte": "futbol",
        "emoji": "⚽",
        "temporada_anyo_dual": True,
    },
    "premier": {
        "id_liga": 4328,
        "nombre": "Premier League",
        "deporte": "futbol",
        "emoji": "⚽",
        "temporada_anyo_dual": True,
    },
    "nba": {
        "id_liga": 4387,
        "nombre": "NBA",
        "deporte": "basket",
        "emoji": "🏀",
        "temporada_anyo_dual": True,
    },
    "mlb": {
        "id_liga": 4424,
        "nombre": "MLB",
        "deporte": "beisbol",
        "emoji": "⚾",
        "temporada_anyo_dual": False,
    },
}

CACHE_DIR = Path.home() / ".cache" / "clima_widget"
CACHE_FILE = CACHE_DIR / "equipos.json"
CACHE_TTL = 6 * 3600  # 6 h

_cache_equipos: dict[str, list[dict[str, str]]] = {}


def _temporada(liga_alias: str) -> str:
    info = LIGAS_TSD.get(liga_alias) or {}
    n = datetime.now()
    if info.get("temporada_anyo_dual"):
        if n.month >= 7:
            return f"{n.year}-{n.year + 1}"
        return f"{n.year - 1}-{n.year}"
    if n.month < 4:
        return str(n.year - 1)
    return str(n.year)


def _cargar_cache_equipos() -> dict[str, Any]:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_cache_equipos(c: dict[str, Any]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _http_json(url: str, timeout: float = 12.0) -> Any:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _fmt_dt_iso(s: str | None, hora: str | None = None) -> tuple[datetime | None, str]:
    if not s:
        return None, ""
    raw = s
    if hora:
        raw = f"{s}T{hora}"
    raw = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        try:
            dt = datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None, ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    hoy = datetime.now().astimezone().date()
    if local.date() == hoy:
        etiqueta = f"hoy · {local.strftime('%H:%M')}"
    else:
        etiqueta = local.strftime("%d %b · %H:%M")
    return local, etiqueta


def _dt_evento_utc(e: dict[str, Any]) -> datetime | None:
    fecha_iso = e.get("dateEvent") or ""
    hora_iso = e.get("strTime") or ""
    dt, _ = _fmt_dt_iso(fecha_iso, hora_iso or None)
    return dt


def _tsd_evento_finalizado_raw(e: dict[str, Any]) -> bool:
    """True si el JSON de TheSportsDB indica partido acabado (no solo listas next/last).

    MLB usa NS, IN1…IN9 y FT según la documentación del API.
    """
    s = (e.get("strStatus") or "").strip().upper()
    if not s:
        return False
    if s in {"NS", "NOT STARTED", "TBD", "SCHEDULED"}:
        return False
    if len(s) >= 3 and s.startswith("IN") and s[2:].isdigit():
        return False
    if s in {"POST", "CANC", "INTR", "ABD"}:
        return False
    final = {
        "FT",
        "AET",
        "FINAL",
        "MATCH FINISHED",
        "GAME FINISHED",
    }
    if s in final or "FINISHED" in s:
        return True
    return False


def _evento_parece_finalizado_api_desfasada(e: dict[str, Any]) -> bool:
    """Si eventsnext sigue en NS pero el partido ya pasó hace horas, confirmar con lookupevent."""
    s = (e.get("strStatus") or "").strip().upper()
    if s and s != "NS":
        return False
    dt = _dt_evento_utc(e)
    if not dt:
        return False
    ahora = datetime.now(dt.tzinfo or timezone.utc)
    if ahora < dt + timedelta(hours=4):
        return False
    id_ev = e.get("idEvent")
    if not id_ev:
        return False
    det = lookup_evento_tsd(str(id_ev))
    if not det:
        return False
    return (det.get("estado") or "") == "Final"


def equipos_de_liga(liga_alias: str, forzar: bool = False) -> list[dict[str, str]]:
    """Devuelve la lista de equipos de la liga (id, nombre)."""
    info = LIGAS_TSD.get(liga_alias)
    if not info:
        return []
    if not forzar and liga_alias in _cache_equipos:
        return _cache_equipos[liga_alias]
    disco = _cargar_cache_equipos()
    entry = disco.get(liga_alias) or {}
    if (
        not forzar
        and entry.get("equipos")
        and time.time() - float(entry.get("ts", 0)) < CACHE_TTL
    ):
        _cache_equipos[liga_alias] = entry["equipos"]
        return entry["equipos"]

    temporada = _temporada(liga_alias)
    url = f"{TSD_BASE}/eventsseason.php?id={info['id_liga']}&s={temporada}"
    try:
        j = _http_json(url, timeout=12)
    except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError):
        return entry.get("equipos") or []
    eventos = j.get("events") or []
    if not eventos and info.get("temporada_anyo_dual"):
        n = datetime.now()
        alt = f"{n.year - 1}-{n.year}" if n.month >= 7 else f"{n.year}-{n.year + 1}"
        try:
            j = _http_json(
                f"{TSD_BASE}/eventsseason.php?id={info['id_liga']}&s={alt}",
                timeout=12,
            )
            eventos = j.get("events") or []
        except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError):
            pass

    vistos: dict[str, str] = {}

    def _cosechar(lista: list[dict[str, Any]]) -> None:
        for e in lista:
            for clave_id, clave_nb in (
                ("idHomeTeam", "strHomeTeam"),
                ("idAwayTeam", "strAwayTeam"),
            ):
                iid = e.get(clave_id)
                nb = e.get(clave_nb)
                if iid and nb and iid not in vistos:
                    vistos[str(iid)] = str(nb)

    _cosechar(eventos)
    for endpoint in ("eventsnextleague.php", "eventspastleague.php"):
        try:
            jx = _http_json(
                f"{TSD_BASE}/{endpoint}?id={info['id_liga']}", timeout=10
            )
            extra = jx.get("events") or jx.get("results") or []
            _cosechar(extra)
        except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError):
            pass

    equipos = [
        {"id": iid, "nombre": nb, "alias": "", "liga": liga_alias}
        for iid, nb in sorted(vistos.items(), key=lambda kv: kv[1])
    ]
    _cache_equipos[liga_alias] = equipos
    if equipos:
        disco[liga_alias] = {"ts": time.time(), "equipos": equipos}
        _guardar_cache_equipos(disco)
    return equipos


def _normaliza(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _puntua(obj: str, candidato: str) -> float:
    """0..1 por similitud, palabra completa."""
    if not obj or not candidato:
        return 0.0
    if obj == candidato:
        return 1.0
    tobj = {t for t in obj.split() if len(t) > 2}
    tcan = {t for t in candidato.split() if len(t) > 2}
    if not tobj or not tcan:
        return 0.4 if (obj in candidato or candidato in obj) else 0.0
    inter = tobj & tcan
    if not inter:
        return 0.0
    return len(inter) / max(len(tobj), 1)


def buscar_equipo(nombre: str, liga_alias: str | None = None) -> dict[str, str] | None:
    if not nombre:
        return None
    obj = _normaliza(nombre)

    def _mejor_en(la: str) -> tuple[dict[str, str] | None, float]:
        equipos = equipos_de_liga(la)
        mejor: dict[str, str] | None = None
        mejor_p = 0.0
        for eq in equipos:
            p = _puntua(obj, _normaliza(eq.get("nombre", "")))
            if p > mejor_p:
                mejor = eq
                mejor_p = p
        return mejor, mejor_p

    mejor: dict[str, str] | None = None
    mejor_p = 0.0
    mejor_la = liga_alias
    if liga_alias:
        eq, p = _mejor_en(liga_alias)
        if eq:
            mejor = eq
            mejor_p = p
            mejor_la = liga_alias
    if mejor_p < 1.0:
        for la in LIGAS_TSD.keys():
            if la == liga_alias:
                continue
            eq, p = _mejor_en(la)
            if p > mejor_p:
                mejor = eq
                mejor_p = p
                mejor_la = la
    if mejor and mejor_p >= 0.5:
        return dict(mejor, liga=mejor_la or mejor.get("liga", ""))
    return None


def _eventos_thesportsdb(id_equipo: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    last: list[dict[str, Any]] = []
    nxt: list[dict[str, Any]] = []
    try:
        last_j = _http_json(f"{TSD_BASE}/eventslast.php?id={id_equipo}", timeout=10)
        last = last_j.get("results") or []
    except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError):
        pass
    try:
        next_j = _http_json(f"{TSD_BASE}/eventsnext.php?id={id_equipo}", timeout=10)
        nxt = next_j.get("events") or []
    except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError):
        pass
    return last, nxt


def _formatear_evento_tsd(
    e: dict[str, Any], *, terminado: bool
) -> dict[str, Any]:
    home = (e.get("strHomeTeam") or "—")[:18]
    away = (e.get("strAwayTeam") or "—")[:18]
    sh = e.get("intHomeScore")
    sa = e.get("intAwayScore")
    try:
        sh = int(sh) if sh not in (None, "") else None
    except (TypeError, ValueError):
        sh = None
    try:
        sa = int(sa) if sa not in (None, "") else None
    except (TypeError, ValueError):
        sa = None
    fecha_iso = e.get("dateEvent") or ""
    hora_iso = e.get("strTime") or ""
    dt, fecha_txt = _fmt_dt_iso(fecha_iso, hora_iso or None)
    estado_raw = (e.get("strStatus") or "").strip()
    progreso = (e.get("strProgress") or "").strip()
    return {
        "id": str(e.get("idEvent") or "") or None,
        "home": home,
        "away": away,
        "home_full": e.get("strHomeTeam") or home,
        "away_full": e.get("strAwayTeam") or away,
        "score_home": sh,
        "score_away": sa,
        "fecha": fecha_txt,
        "fecha_iso": fecha_iso,
        "hora_iso": hora_iso,
        "dt_utc": dt.isoformat() if dt else None,
        "estado": "Final" if terminado else "Programado",
        "estado_raw": estado_raw,
        "progreso": progreso,
        "sede": e.get("strVenue") or "",
        "ciudad": e.get("strCity") or "",
        "liga": e.get("strLeague") or "",
        "temporada": e.get("strSeason") or "",
        "ronda": e.get("intRound") or "",
        "espectadores": e.get("intSpectators") or "",
        "tv": e.get("strTvStation") or "",
        "thumb": e.get("strThumb") or "",
        "video": e.get("strVideo") or "",
    }


def lookup_evento_tsd(id_evento: str) -> dict[str, Any] | None:
    """Detalle / estado actual de un evento concreto."""
    if not id_evento:
        return None
    try:
        j = _http_json(
            f"{TSD_BASE}/lookupevent.php?id={id_evento}", timeout=10
        )
    except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError):
        return None
    eventos = j.get("events") or []
    if not eventos:
        return None
    e = eventos[0]
    terminado = _tsd_evento_finalizado_raw(e)
    return _formatear_evento_tsd(e, terminado=terminado)


def traer_equipo(equipo_cfg: dict[str, str]) -> dict[str, Any]:
    """Recibe {liga, nombre, [id]} y devuelve {prev, next, titulo, emoji}."""
    liga = equipo_cfg.get("liga", "")
    info_liga = LIGAS_TSD.get(liga)
    if not info_liga:
        return {"err": f"Liga no soportada: {liga}"}
    id_equipo = equipo_cfg.get("id") or ""
    if not id_equipo and equipo_cfg.get("nombre"):
        eq = buscar_equipo(equipo_cfg["nombre"], liga)
        if eq:
            id_equipo = eq.get("id") or ""
    if not id_equipo:
        return {"err": f"No encontrado: {equipo_cfg.get('nombre')}"}
    try:
        last, nxt = _eventos_thesportsdb(id_equipo)
    except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError) as e:
        return {"err": str(e)}

    # La API a veces deja partidos ya terminados (FT) en eventsnext.php; unificamos con eventslast.
    cola_next = list(nxt)
    candidatos_prev: list[dict[str, Any]] = []
    if last:
        candidatos_prev.append(last[0])
    while cola_next:
        primero = cola_next[0]
        if _tsd_evento_finalizado_raw(primero):
            candidatos_prev.append(cola_next.pop(0))
            continue
        if _evento_parece_finalizado_api_desfasada(primero):
            candidatos_prev.append(cola_next.pop(0))
            continue
        break

    def _clave_reciente(e: dict[str, Any]) -> float:
        dt = _dt_evento_utc(e)
        return dt.timestamp() if dt else 0.0

    prev_raw = (
        max(candidatos_prev, key=_clave_reciente) if candidatos_prev else None
    )
    sig_raw = cola_next[0] if cola_next else None

    prev = (
        _formatear_evento_tsd(prev_raw, terminado=True) if prev_raw else None
    )
    sig = (
        _formatear_evento_tsd(sig_raw, terminado=False) if sig_raw else None
    )
    return {
        "prev": prev,
        "next": sig,
        "titulo": equipo_cfg.get("nombre") or info_liga["nombre"],
        "emoji": info_liga["emoji"],
        "liga": info_liga["nombre"],
    }


def _formatear_carrera_f1(
    r: dict[str, Any], *, resultados: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    nombre = (r.get("raceName") or "GP")[:22]
    nombre_full = r.get("raceName") or "GP"
    circuito = (r.get("Circuit") or {})
    nom_circ = circuito.get("circuitName") or ""
    loc = circuito.get("Location") or {}
    pais = loc.get("country") or ""
    ciudad = loc.get("locality") or ""
    fecha_iso = r.get("date") or ""
    hora_iso = r.get("time") or ""
    dt, fecha_txt = _fmt_dt_iso(fecha_iso, hora_iso or None)
    out: dict[str, Any] = {
        "id": None,
        "home": nombre,
        "away": pais[:14],
        "home_full": nombre_full,
        "away_full": pais,
        "fecha": fecha_txt,
        "fecha_iso": fecha_iso,
        "hora_iso": hora_iso,
        "dt_utc": dt.isoformat() if dt else None,
        "estado": "Programado",
        "estado_raw": "",
        "score_home": None,
        "score_away": None,
        "sede": nom_circ,
        "ciudad": ciudad,
        "liga": "Fórmula 1",
        "ronda": str(r.get("round") or ""),
        "temporada": str(r.get("season") or ""),
        "podio": [],
        "es_f1": True,
    }
    if resultados:
        podio = []
        for pos in ("1", "2", "3"):
            row = next(
                (r2 for r2 in resultados if str(r2.get("position")) == pos), None
            )
            if row:
                d = row.get("Driver") or {}
                podio.append(
                    {
                        "pos": pos,
                        "nombre": f"{d.get('givenName', '')} {d.get('familyName', '')}".strip(),
                        "apellido": d.get("familyName") or "",
                        "equipo": (row.get("Constructor") or {}).get("name") or "",
                        "tiempo": (row.get("Time") or {}).get("time")
                        or row.get("status")
                        or "",
                    }
                )
        out["podio"] = podio
        if podio:
            ganador = podio[0]
            out["away"] = ganador["apellido"][:14]
            out["estado"] = (
                f"🏁 {ganador['equipo']}" if ganador["equipo"] else "Final"
            )
    return out


def traer_f1() -> dict[str, Any]:
    """Última carrera + próxima del calendario actual."""
    try:
        cal = _http_json(f"{JOLPICA_BASE}/current.json", timeout=10)
    except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError) as e:
        return {"err": str(e)}
    races = ((cal.get("MRData") or {}).get("RaceTable") or {}).get("Races") or []
    if not races:
        return {"err": "Sin calendario F1"}

    ahora = datetime.now(timezone.utc)
    prev_race = None
    next_race = None
    for r in races:
        fecha_iso = r.get("date") or ""
        hora_iso = r.get("time") or ""
        dt, _ = _fmt_dt_iso(fecha_iso, hora_iso or None)
        if not dt:
            continue
        if dt < ahora:
            prev_race = r
        elif next_race is None:
            next_race = r

    resultados = []
    if prev_race is not None:
        ronda = prev_race.get("round")
        season = prev_race.get("season") or "current"
        try:
            res_j = _http_json(
                f"{JOLPICA_BASE}/{season}/{ronda}/results.json", timeout=10
            )
            res_races = (
                (res_j.get("MRData") or {}).get("RaceTable", {}).get("Races") or []
            )
            if res_races:
                resultados = res_races[0].get("Results") or []
        except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError):
            resultados = []

    return {
        "prev": _formatear_carrera_f1(prev_race, resultados=resultados) if prev_race else None,
        "next": _formatear_carrera_f1(next_race) if next_race else None,
        "titulo": f"F1 · {races[0].get('season')}",
        "emoji": "🏎️",
        "liga": "Fórmula 1",
    }


class TarjetaPartido(QFrame):
    """Tarjeta horizontal con último resultado y próximo partido de un equipo."""

    clic = pyqtSignal()

    def __init__(self, titulo: str, emoji: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardDeporte")
        self.setAutoFillBackground(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        cab = QHBoxLayout()
        cab.setSpacing(8)
        self._em = QLabel(emoji)
        self._em.setObjectName("cardEmoji")
        self._tit = QLabel(titulo.upper())
        self._tit.setObjectName("cardTitulo")
        self._tit.setWordWrap(True)
        cab.addWidget(self._em, 0)
        cab.addWidget(self._tit, 1)
        v.addLayout(cab)
        self.setMinimumWidth(180)

        self._caja_prev = self._caja(v, "ÚLTIMO")
        self._caja_next = self._caja(v, "PRÓXIMO")
        self._datos: dict[str, Any] = {}

    def datos(self) -> dict[str, Any]:
        return self._datos

    def mousePressEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if e.button() == Qt.MouseButton.LeftButton:
            self.clic.emit()
            e.accept()
            return
        super().mousePressEvent(e)

    def set_titulo(self, titulo: str, emoji: str | None = None) -> None:
        self._tit.setText(titulo.upper())
        if emoji:
            self._em.setText(emoji)

    def _caja(self, padre_lay: QVBoxLayout, etiqueta: str) -> dict[str, Any]:
        wrap = QFrame()
        wrap.setObjectName("subcardDeporte")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)

        cabecera = QHBoxLayout()
        et = QLabel(etiqueta)
        et.setObjectName("subcardEtiqueta")
        fecha = QLabel("")
        fecha.setObjectName("subcardFecha")
        fecha.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        cabecera.addWidget(et, 1)
        cabecera.addWidget(fecha, 0)
        lay.addLayout(cabecera)

        marcador = QHBoxLayout()
        marcador.setSpacing(6)
        home = QLabel("—")
        home.setObjectName("subcardEquipo")
        home.setWordWrap(True)
        score = QLabel("·")
        score.setObjectName("subcardMarcador")
        score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        away = QLabel("—")
        away.setObjectName("subcardEquipo")
        away.setWordWrap(True)
        away.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        marcador.addWidget(home, 1)
        marcador.addWidget(score, 0)
        marcador.addWidget(away, 1)
        lay.addLayout(marcador)

        padre_lay.addWidget(wrap)
        return {
            "wrap": wrap,
            "fecha": fecha,
            "home": home,
            "away": away,
            "score": score,
        }

    def actualizar(self, datos: dict[str, Any]) -> None:
        self._datos = dict(datos or {})
        if datos.get("titulo"):
            self.set_titulo(str(datos["titulo"]), datos.get("emoji"))
        if datos.get("err"):
            self._caja_prev["fecha"].setText("")
            self._caja_prev["home"].setText("Sin datos")
            self._caja_prev["away"].setText("")
            self._caja_prev["score"].setText("·")
            self._caja_next["fecha"].setText("")
            self._caja_next["home"].setText(str(datos["err"])[:40])
            self._caja_next["away"].setText("")
            self._caja_next["score"].setText("·")
            return
        self._pintar(self._caja_prev, datos.get("prev"), terminado=True)
        self._pintar(self._caja_next, datos.get("next"), terminado=False)

    @staticmethod
    def _pintar(caja: dict[str, Any], p: dict[str, Any] | None, *, terminado: bool) -> None:
        if not p:
            caja["fecha"].setText("—")
            caja["home"].setText("Sin partidos")
            caja["away"].setText("")
            caja["score"].setText("·")
            return
        caja["fecha"].setText(p.get("fecha") or p.get("estado") or "")
        caja["home"].setText(str(p.get("home") or "—"))
        caja["away"].setText(str(p.get("away") or "—"))
        sh = p.get("score_home")
        sa = p.get("score_away")
        if sh is not None and sa is not None:
            caja["score"].setText(f"{sh}  –  {sa}")
        elif terminado and p.get("estado", "").startswith("🏁"):
            caja["score"].setText(p["estado"])
        else:
            caja["score"].setText("vs")

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self.setStyleSheet(
            f"""
            QFrame#cardDeporte {{
                background-color: {tema["card"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 18px;
            }}
            QFrame#subcardDeporte {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
            }}
            QLabel#cardEmoji {{ font-size: 22px; }}
            QLabel#cardTitulo {{
                color: {tema["sec"]};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.22em;
            }}
            QLabel#subcardEtiqueta {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.2em;
            }}
            QLabel#subcardFecha {{
                color: {tema["mut"]};
                font-size: 10px;
                font-weight: 500;
            }}
            QLabel#subcardEquipo {{
                color: {tema["titulo"]};
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#subcardMarcador {{
                color: {tema["acento"]};
                font-size: 14px;
                font-weight: 700;
                min-width: 56px;
            }}
            """
        )
