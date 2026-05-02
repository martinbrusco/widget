#!/usr/bin/env python3
"""Clima + Sistema + Deportes (Dodgers · Bayern Múnich)."""

from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pyqtgraph as pg
from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QCloseEvent,
    QColor,
    QCursor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from clima_alertas import resumen_alertas, traer_alertas_meteo
from descargas_media import (
    CALIDADES_VIDEO,
    construir_opciones,
    ejecutar_descarga,
    es_url_permitida,
    limpiar_mensaje_error,
    yt_dlp_instalado,
)
from noticias import obtener_top_noticias
from deportes import (
    TarjetaPartido,
    buscar_equipo,
    equipos_de_liga,
    lookup_evento_tsd,
    traer_equipo,
    traer_f1,
)
from metricas import (
    COLORES_SERIE,
    MonitorApps,
    MonitorRed,
    PanelMultiSerie,
    PanelSerie,
    accion_docker,
    cambiar_fan,
    cambiar_turbo,
    cpu_freq_resumen,
    estado_fan,
    estado_turbo,
    evaluar_temperaturas,
    filtrar_temperaturas,
    fmt_bytes,
    fmt_seg,
    ip_local,
    ip_publica,
    listar_docker,
    matar_proceso,
    notificar_escritorio,
    ping_ms,
    recolectar_baterias,
    recolectar_gpu,
    recolectar_metricas,
    signal_dbm,
    stats_docker,
    umbrales_temperatura,
)
from pensamientos import cita_del_dia
from sistema_solar import MapaSistemaSolar, PanelInfoPlaneta, posiciones_planetas
from mundo_simple import CONTINENTES
import autostart
from paneles import (
    PanelClima,
    PanelDeportes,
    PanelDescargas,
    PanelMetricasEquipo,
    PanelNoticiasFeed,
    PanelSolarDashboard,
)


def carpeta_descargas_por_defecto() -> Path:
    xd = os.environ.get("XDG_DOWNLOAD_DIR", "").strip().strip('"')
    if xd:
        p = Path(xd.replace("$HOME", str(Path.home())))
        if p.is_dir():
            return p
    for nombre in ("Descargas", "Downloads", "descargas"):
        p = Path.home() / nombre
        if p.is_dir():
            return p
    return Path.home() / "Descargas"

LAT = 40.3057
LON = -3.7327
CIUDAD = "Getafe"
REGION_ALERTAS_DEFECTO = "Madrid"
HEADERS = {"User-Agent": "ClimaWidget/1.0"}

CONFIG_DIR = Path.home() / ".config"
CONFIG_FILE = CONFIG_DIR / "clima_widget.json"

_MESES = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)
_DIAS = (
    "lunes", "martes", "miércoles", "jueves",
    "viernes", "sábado", "domingo",
)


def texto_fecha_es(ahora: datetime | None = None) -> str:
    d = ahora or datetime.now()
    return f"{_DIAS[d.weekday()]} · {d.day} {_MESES[d.month - 1]}"


def rosa_viento(grados: float | None) -> str:
    if grados is None:
        return ""
    dirs = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
    i = int((float(grados) + 22.5) // 45) % 8
    return dirs[i]


def color_acento(code: int, es_dia: bool) -> str:
    if not es_dia:
        return "#c4b5fd"
    if code == 0:
        return "#fde047"
    if code in (61, 63, 65, 80, 81, 82, 95, 96, 99):
        return "#22d3ee"
    if code in (71, 73, 75, 85, 86):
        return "#e0f2fe"
    return "#7dd3fc"


def wmo_emoji(c: int) -> str:
    if c == 0:
        return "☀️"
    if c in (1, 2, 3):
        return "⛅"
    if c in (45, 48):
        return "🌫️"
    if c in (61, 63, 65, 80, 81, 82):
        return "🌧️"
    if c in (71, 73, 75, 85, 86):
        return "❄️"
    if c in (95, 96, 99):
        return "⛈️"
    return "🌤️"


def wmo_txt(c: int) -> str:
    if c == 0:
        return "Despejado"
    if c in (1, 2, 3):
        return "Parcialmente nublado"
    if c in (45, 48):
        return "Niebla"
    if c in (61, 63, 65, 80, 81, 82):
        return "Lluvia"
    if c in (71, 73, 75, 85, 86):
        return "Nieve"
    if c in (95, 96, 99):
        return "Tormenta"
    return "Variable"


_TEMA_CLARO = {
    "g0": "#e2e8f0",
    "g1": "#cbd5e1",
    "borde": "rgba(15,23,42,0.12)",
    "titulo": "#0f172a",
    "sec": "rgba(15,23,42,0.85)",
    "mut": "rgba(15,23,42,0.55)",
    "raya": "rgba(15,23,42,0.12)",
    "acento": "#0ea5e9",
    "card": "rgba(15,23,42,0.06)",
    "card_borde": "rgba(15,23,42,0.12)",
}


def tema_visual(code: int, es_dia: bool, claro_forzado: bool = False) -> dict[str, str]:
    if claro_forzado:
        return dict(_TEMA_CLARO)
    ac = color_acento(code, es_dia)
    if not es_dia:
        return {
            "g0": "#0a0618", "g1": "#1e2f6b",
            "borde": "rgba(196,181,253,0.18)",
            "titulo": "#f8fafc", "sec": "rgba(226,232,240,0.9)",
            "mut": "rgba(148,163,184,0.78)",
            "raya": "rgba(255,255,255,0.12)", "acento": ac,
            "card": "rgba(255,255,255,0.06)",
            "card_borde": "rgba(255,255,255,0.14)",
        }
    if code == 0:
        return {
            "g0": "#0e3a8a", "g1": "#60a5fa",
            "borde": "rgba(255,255,255,0.28)",
            "titulo": "#ffffff", "sec": "rgba(255,255,255,0.95)",
            "mut": "rgba(255,255,255,0.72)",
            "raya": "rgba(255,255,255,0.32)", "acento": ac,
            "card": "rgba(255,255,255,0.12)",
            "card_borde": "rgba(255,255,255,0.22)",
        }
    if code in (1, 2, 3):
        return {
            "g0": "#334155", "g1": "#7c93ad",
            "borde": "rgba(255,255,255,0.2)",
            "titulo": "#ffffff", "sec": "rgba(248,250,252,0.95)",
            "mut": "rgba(226,232,240,0.78)",
            "raya": "rgba(255,255,255,0.28)", "acento": ac,
            "card": "rgba(255,255,255,0.09)",
            "card_borde": "rgba(255,255,255,0.18)",
        }
    if code in (61, 63, 65, 80, 81, 82, 95, 96, 99):
        return {
            "g0": "#1f2937", "g1": "#475569",
            "borde": "rgba(255,255,255,0.16)",
            "titulo": "#f8fafc", "sec": "rgba(241,245,249,0.92)",
            "mut": "rgba(203,213,225,0.72)",
            "raya": "rgba(255,255,255,0.22)", "acento": ac,
            "card": "rgba(255,255,255,0.07)",
            "card_borde": "rgba(255,255,255,0.14)",
        }
    if code in (71, 73, 75, 85, 86):
        return {
            "g0": "#3b5f7a", "g1": "#a8c4d4",
            "borde": "rgba(255,255,255,0.2)",
            "titulo": "#ffffff", "sec": "rgba(255,255,255,0.94)",
            "mut": "rgba(226,232,240,0.75)",
            "raya": "rgba(255,255,255,0.28)", "acento": ac,
            "card": "rgba(255,255,255,0.1)",
            "card_borde": "rgba(255,255,255,0.18)",
        }
    if code in (45, 48):
        return {
            "g0": "#374151", "g1": "#9ca3af",
            "borde": "rgba(255,255,255,0.15)",
            "titulo": "#f9fafb", "sec": "rgba(243,244,246,0.9)",
            "mut": "rgba(209,213,219,0.65)",
            "raya": "rgba(255,255,255,0.2)", "acento": ac,
            "card": "rgba(255,255,255,0.07)",
            "card_borde": "rgba(255,255,255,0.14)",
        }
    return {
        "g0": "#1e3a8a", "g1": "#7dd3fc",
        "borde": "rgba(255,255,255,0.22)",
        "titulo": "#ffffff", "sec": "rgba(255,255,255,0.92)",
        "mut": "rgba(255,255,255,0.7)",
        "raya": "rgba(255,255,255,0.28)", "acento": ac,
        "card": "rgba(255,255,255,0.09)",
        "card_borde": "rgba(255,255,255,0.18)",
    }


def traer_clima() -> dict[str, Any]:
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,apparent_temperature,weather_code,"
        "relative_humidity_2m,is_day,wind_speed_10m,wind_direction_10m"
        "&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset"
        "&forecast_days=2"
        "&timezone=Europe%2FMadrid"
    )
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode("utf-8"))
    cur = j.get("current") or {}
    es_dia = bool(cur.get("is_day", 1))
    wsp = cur.get("wind_speed_10m")
    wind_kmh = float(wsp) * 3.6 if wsp is not None else None
    wd = cur.get("wind_direction_10m")
    wind_deg = float(wd) if wd is not None else None
    daily = j.get("daily") or {}
    out_d: dict[str, Any] = {}
    for clave_origen, clave_dest in (
        ("temperature_2m_max", "tmax"),
        ("temperature_2m_min", "tmin"),
        ("sunrise", "sunrise"),
        ("sunset", "sunset"),
    ):
        valores = daily.get(clave_origen) or []
        out_d[f"{clave_dest}_hoy"] = valores[0] if len(valores) > 0 else None
        out_d[f"{clave_dest}_mna"] = valores[1] if len(valores) > 1 else None
    return {
        "t": cur.get("temperature_2m"),
        "apparent": cur.get("apparent_temperature"),
        "code": int(cur.get("weather_code") or 0),
        "hum": cur.get("relative_humidity_2m"),
        "es_dia": es_dia,
        "wind_kmh": wind_kmh,
        "wind_deg": wind_deg,
        **out_d,
    }


def cargar_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_config(cfg: dict[str, Any]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        pass


class Senales(QObject):
    clima = pyqtSignal(object)
    deportes = pyqtSignal(object)
    alertas = pyqtSignal(object)
    descarga_progreso = pyqtSignal(str)
    descarga_fin = pyqtSignal(bool, str)
    noticias = pyqtSignal(object)


class Arrastrar:
    _p: QPoint | None = None

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._p = (
                e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._p is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._p)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._p = None
        super().mouseReleaseEvent(e)


class Barra(Arrastrar, QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("barra")
        self.setAutoFillBackground(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 16, 18, 8)
        marca = QLabel("◎")
        marca.setObjectName("marcaBarra")
        hint = QLabel("arrastra · redimensiona en los bordes · clic derecho")
        hint.setObjectName("hint")
        hint.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        lay.addWidget(marca, 0)
        lay.addStretch(1)
        lay.addWidget(hint, 0)


class TarjetaBateria(QFrame):
    """Fila horizontal: emoji · nombre/estado · barra · porcentaje."""

    def __init__(self, info: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardBateria")
        self.setAutoFillBackground(False)
        L = QHBoxLayout(self)
        L.setContentsMargins(14, 10, 14, 10)
        L.setSpacing(12)

        self._em = QLabel(info.get("emoji") or "🔋")
        self._em.setObjectName("batEmoji")

        col = QVBoxLayout()
        col.setSpacing(2)
        self._nombre = QLabel(info.get("nombre") or "Batería")
        self._nombre.setObjectName("batNombre")
        self._estado = QLabel("")
        self._estado.setObjectName("batEstado")
        col.addWidget(self._nombre)
        col.addWidget(self._estado)

        self._bar = QProgressBar()
        self._bar.setObjectName("batBarra")
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)

        self._pct = QLabel("—")
        self._pct.setObjectName("batPct")
        self._pct.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        L.addWidget(self._em, 0)
        L.addLayout(col, 0)
        L.addWidget(self._bar, 1)
        L.addWidget(self._pct, 0)
        self._info = info
        self._tema: dict[str, str] = {}
        self.actualizar(info)

    @staticmethod
    def _texto_estado(info: dict[str, Any]) -> str:
        st = (info.get("status") or "").lower()
        tipo = info.get("tipo") or ""
        if tipo == "laptop":
            if "charging" in st:
                return "cargando · portátil"
            if "discharging" in st:
                return "en uso · portátil"
            if "full" in st or "not charging" in st:
                return "conectado · portátil"
            return "portátil"
        if tipo == "mouse":
            return "ratón Bluetooth"
        if tipo == "audio":
            return "audio Bluetooth"
        if tipo == "teclado":
            return "teclado Bluetooth"
        if tipo == "gamepad":
            return "mando Bluetooth"
        if tipo == "bt":
            return "dispositivo Bluetooth"
        return ""

    def _color_para_pct(self, pct: int) -> str:
        if pct < 20:
            return "#ef4444"
        if pct < 40:
            return "#f59e0b"
        return self._tema.get("acento") or "#22d3ee"

    def actualizar(self, info: dict[str, Any]) -> None:
        self._info = info
        self._em.setText(info.get("emoji") or "🔋")
        self._nombre.setText(info.get("nombre") or "Batería")
        self._estado.setText(self._texto_estado(info))
        pct = int(info.get("pct") or 0)
        self._bar.setValue(pct)
        self._pct.setText(f"{pct} %")
        self._aplicar_estilos()

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self.actualizar(self._info)

    def _aplicar_estilos(self) -> None:
        t = self._tema
        if not t:
            return
        col = self._color_para_pct(int(self._info.get("pct") or 0))
        self.setStyleSheet(
            f"""
            QFrame#cardBateria {{
                background-color: {t["card"]};
                border: 1px solid {t["card_borde"]};
                border-radius: 14px;
            }}
            QLabel#batEmoji {{ font-size: 18px; }}
            QLabel#batNombre {{
                color: {t["titulo"]};
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#batEstado {{
                color: {t["mut"]};
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 0.12em;
            }}
            QLabel#batPct {{
                color: {t["sec"]};
                font-size: 13px;
                font-weight: 700;
                min-width: 42px;
            }}
            QProgressBar#batBarra {{
                border: none;
                background: rgba(255,255,255,0.1);
                border-radius: 3px;
            }}
            QProgressBar#batBarra::chunk {{
                background-color: {col};
                border-radius: 3px;
            }}
            """
        )


def _fmt_uptime(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


class TarjetaWifi(QFrame):
    """Tarjeta Wi-Fi: SSID, dBm, ping, IPs, tráfico acumulado y mini gráfica RX/TX."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardWifi")
        self.setAutoFillBackground(False)
        L = QVBoxLayout(self)
        L.setContentsMargins(16, 14, 16, 14)
        L.setSpacing(10)

        cab = QHBoxLayout()
        cab.setSpacing(8)
        em = QLabel("📶")
        em.setObjectName("wifiEmoji")
        col = QVBoxLayout()
        col.setSpacing(2)
        self._ssid = QLabel("—")
        self._ssid.setObjectName("wifiSsid")
        self._iface = QLabel("")
        self._iface.setObjectName("wifiIface")
        col.addWidget(self._ssid)
        col.addWidget(self._iface)
        col_d = QVBoxLayout()
        col_d.setSpacing(2)
        self._dbm = QLabel("— dBm")
        self._dbm.setObjectName("wifiDbm")
        self._dbm.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._uptime = QLabel("—")
        self._uptime.setObjectName("wifiUptime")
        self._uptime.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        col_d.addWidget(self._dbm)
        col_d.addWidget(self._uptime)
        cab.addWidget(em, 0)
        cab.addLayout(col, 1)
        cab.addLayout(col_d, 0)
        L.addLayout(cab)

        fila_ips = QHBoxLayout()
        fila_ips.setSpacing(10)
        self._chip_ping = self._chip_info("Ping", "—")
        self._chip_local = self._chip_info("IP local", "—")
        self._chip_pub = self._chip_info("IP pública", "…")
        fila_ips.addWidget(self._chip_ping["wrap"], 1)
        fila_ips.addWidget(self._chip_local["wrap"], 1)
        fila_ips.addWidget(self._chip_pub["wrap"], 1)
        L.addLayout(fila_ips)

        fila = QHBoxLayout()
        fila.setSpacing(10)
        self._caja_rx = self._caja("Descargado", "↓")
        self._caja_tx = self._caja("Subido", "↑")
        fila.addWidget(self._caja_rx["wrap"], 1)
        fila.addWidget(self._caja_tx["wrap"], 1)
        L.addLayout(fila)

        self._panel_red = PanelMultiSerie(
            "Tráfico (KB/s)", " KB/s", 0, 100, altura=80, maxlen=120
        )
        L.addWidget(self._panel_red)
        self._tema: dict[str, str] = {}

    def _chip_info(self, etiqueta: str, valor: str) -> dict[str, Any]:
        wrap = QFrame()
        wrap.setObjectName("wifiChip")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(0)
        et = QLabel(etiqueta.upper())
        et.setObjectName("wifiChipEt")
        val = QLabel(valor)
        val.setObjectName("wifiChipVal")
        v.addWidget(et)
        v.addWidget(val)
        return {"wrap": wrap, "valor": val, "etiqueta": et}

    def _caja(self, etiqueta: str, simbolo: str) -> dict[str, Any]:
        wrap = QFrame()
        wrap.setObjectName("wifiCaja")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(2)
        cab = QHBoxLayout()
        cab.setSpacing(4)
        sim = QLabel(simbolo)
        sim.setObjectName("wifiSimbolo")
        et = QLabel(etiqueta.upper())
        et.setObjectName("wifiCajaEt")
        cab.addWidget(sim, 0)
        cab.addWidget(et, 1)
        valor = QLabel("—")
        valor.setObjectName("wifiCajaValor")
        tasa = QLabel("0 B/s")
        tasa.setObjectName("wifiTasa")
        v.addLayout(cab)
        v.addWidget(valor)
        v.addWidget(tasa)
        return {"wrap": wrap, "valor": valor, "tasa": tasa}

    def actualizar(self, datos: dict[str, Any] | None) -> None:
        if not datos:
            self._ssid.setText("Sin Wi-Fi")
            self._iface.setText("")
            self._dbm.setText("")
            self._uptime.setText("")
            self._caja_rx["valor"].setText("—")
            self._caja_tx["valor"].setText("—")
            self._caja_rx["tasa"].setText("0 B/s")
            self._caja_tx["tasa"].setText("0 B/s")
            self._chip_ping["valor"].setText("—")
            self._chip_local["valor"].setText("—")
            self._chip_pub["valor"].setText("—")
            return
        self._ssid.setText(datos.get("ssid") or "(red Wi-Fi)")
        self._iface.setText(datos.get("iface") or "")
        self._uptime.setText(_fmt_uptime(datos.get("uptime") or 0))
        dbm = datos.get("dbm")
        self._dbm.setText(f"{dbm} dBm" if isinstance(dbm, int) else "")
        self._caja_rx["valor"].setText(fmt_bytes(int(datos.get("sesion_rx") or 0)))
        self._caja_tx["valor"].setText(fmt_bytes(int(datos.get("sesion_tx") or 0)))
        rx_rate = float(datos.get("rx_rate") or 0)
        tx_rate = float(datos.get("tx_rate") or 0)
        self._caja_rx["tasa"].setText(f"{fmt_bytes(int(rx_rate))}/s")
        self._caja_tx["tasa"].setText(f"{fmt_bytes(int(tx_rate))}/s")
        ping = datos.get("ping_ms")
        self._chip_ping["valor"].setText(
            f"{ping:.0f} ms" if isinstance(ping, (int, float)) else "—"
        )
        self._chip_local["valor"].setText(datos.get("ip_local") or "—")
        self._chip_pub["valor"].setText(datos.get("ip_pub") or "…")
        self._panel_red.actualizar(
            [("RX", rx_rate / 1024.0), ("TX", tx_rate / 1024.0)]
        )

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self._panel_red.aplicar_texto_tema(tema["mut"], tema["sec"])
        self.setStyleSheet(
            f"""
            QFrame#cardWifi {{
                background-color: {tema["card"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 16px;
            }}
            QFrame#wifiCaja, QFrame#wifiChip {{
                background-color: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
            }}
            QLabel#wifiEmoji {{ font-size: 18px; }}
            QLabel#wifiSsid {{
                color: {tema["titulo"]};
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.04em;
            }}
            QLabel#wifiIface {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 0.16em;
            }}
            QLabel#wifiDbm {{
                color: {tema["sec"]};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.06em;
            }}
            QLabel#wifiUptime {{
                color: {tema["mut"]};
                font-size: 10px;
                font-weight: 600;
            }}
            QLabel#wifiSimbolo {{
                color: {tema["acento"]};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#wifiCajaEt, QLabel#wifiChipEt {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.18em;
            }}
            QLabel#wifiCajaValor {{
                color: {tema["titulo"]};
                font-size: 18px;
                font-weight: 700;
                letter-spacing: -0.5px;
            }}
            QLabel#wifiChipVal {{
                color: {tema["titulo"]};
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#wifiTasa {{
                color: {tema["sec"]};
                font-size: 10px;
                font-weight: 500;
            }}
            """
        )


class TarjetaDocker(QFrame):
    """Fila Docker: estado · nombre · imagen · CPU% · MEM% · botones."""

    def __init__(self, on_accion, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("filaDocker")
        self.setAutoFillBackground(False)
        self._on_accion = on_accion
        self._nombre_actual = ""
        self._tema: dict[str, str] = {}
        self._estado_color = "#22d3ee"

        L = QVBoxLayout(self)
        L.setContentsMargins(12, 8, 12, 8)
        L.setSpacing(6)

        sup = QHBoxLayout()
        sup.setSpacing(10)
        self._dot = QFrame()
        self._dot.setObjectName("dotDocker")
        self._dot.setFixedSize(8, 8)
        col = QVBoxLayout()
        col.setSpacing(2)
        self._nombre = QLabel("…")
        self._nombre.setObjectName("dockNombre")
        self._sub = QLabel("…")
        self._sub.setObjectName("dockSub")
        col.addWidget(self._nombre)
        col.addWidget(self._sub)
        self._status = QLabel("")
        self._status.setObjectName("dockStatus")
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        sup.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        sup.addLayout(col, 1)
        sup.addWidget(self._status, 0)
        L.addLayout(sup)

        inf = QHBoxLayout()
        inf.setSpacing(10)
        self._cpu = QLabel("CPU —")
        self._cpu.setObjectName("dockMetric")
        self._mem = QLabel("MEM —")
        self._mem.setObjectName("dockMetric")
        self._mem_uso = QLabel("")
        self._mem_uso.setObjectName("dockMetricSub")
        inf.addWidget(self._cpu, 0)
        inf.addWidget(self._mem, 0)
        inf.addWidget(self._mem_uso, 1)

        self._btn_start = QPushButton("▶")
        self._btn_stop = QPushButton("■")
        self._btn_restart = QPushButton("↻")
        for b, accion, tip in (
            (self._btn_start, "start", "Iniciar"),
            (self._btn_stop, "stop", "Parar"),
            (self._btn_restart, "restart", "Reiniciar"),
        ):
            b.setObjectName("dockBtn")
            b.setFixedSize(22, 22)
            b.setToolTip(tip)
            b.clicked.connect(lambda _checked=False, a=accion: self._click(a))
            inf.addWidget(b, 0)
        L.addLayout(inf)

    def _click(self, accion: str) -> None:
        if self._nombre_actual and self._on_accion:
            self._on_accion(self._nombre_actual, accion)

    def actualizar(self, info: dict[str, Any], stats: dict[str, Any] | None = None) -> None:
        self._nombre_actual = str(info.get("nombre") or "")
        self._nombre.setText(self._nombre_actual or "?")
        img = str(info.get("imagen") or "")
        if len(img) > 38:
            img = img[:35] + "…"
        puertos = str(info.get("puertos") or "")
        if puertos and len(puertos) > 24:
            puertos = puertos[:22] + "…"
        sub = " · ".join(s for s in (img, puertos) if s)
        self._sub.setText(sub or "—")
        st = (info.get("estado") or "").lower()
        corriendo = "running" in st or "up" in st
        if corriendo:
            self._estado_color = "#22c55e"
        elif "paused" in st:
            self._estado_color = "#f59e0b"
        elif "exited" in st or "dead" in st or "stopped" in st:
            self._estado_color = "#ef4444"
        elif "restarting" in st:
            self._estado_color = "#a78bfa"
        else:
            self._estado_color = self._tema.get("acento") or "#22d3ee"
        self._status.setText(str(info.get("status") or st or "—")[:32])
        if stats:
            self._cpu.setText(f"CPU {stats.get('cpu_pct', 0):.0f}%")
            self._mem.setText(f"MEM {stats.get('mem_pct', 0):.0f}%")
            self._mem_uso.setText(str(stats.get("mem_uso") or "").split(" / ")[0])
        else:
            self._cpu.setText("CPU —")
            self._mem.setText("MEM —")
            self._mem_uso.setText("")
        self._btn_start.setEnabled(not corriendo)
        self._btn_stop.setEnabled(corriendo)
        self._btn_restart.setEnabled(True)
        self._aplicar_estilo()

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self._aplicar_estilo()

    def _aplicar_estilo(self) -> None:
        t = self._tema
        if not t:
            return
        self.setStyleSheet(
            f"""
            QFrame#filaDocker {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
            }}
            QFrame#dotDocker {{
                background-color: {self._estado_color};
                border-radius: 4px;
            }}
            QLabel#dockNombre {{
                color: {t["titulo"]};
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#dockSub {{
                color: {t["mut"]};
                font-size: 10px;
                font-weight: 500;
                letter-spacing: 0.02em;
            }}
            QLabel#dockStatus {{
                color: {t["sec"]};
                font-size: 10px;
                font-weight: 600;
            }}
            QLabel#dockMetric {{
                color: {t["sec"]};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.04em;
            }}
            QLabel#dockMetricSub {{
                color: {t["mut"]};
                font-size: 9px;
                font-weight: 500;
            }}
            QPushButton#dockBtn {{
                background: rgba(255,255,255,0.06);
                color: {t["sec"]};
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 11px;
                font-size: 10px;
                font-weight: 700;
                padding: 0;
            }}
            QPushButton#dockBtn:hover {{
                background: {t["acento"]};
                color: white;
                border: none;
            }}
            QPushButton#dockBtn:disabled {{
                color: rgba(255,255,255,0.25);
                background: rgba(255,255,255,0.03);
            }}
            """
        )


class TarjetaGpu(QFrame):
    """Tarjeta GPU: vendor, modelo, uso, VRAM, temperatura, mini-gráfica de uso."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardGpu")
        self.setAutoFillBackground(False)
        L = QVBoxLayout(self)
        L.setContentsMargins(14, 12, 14, 12)
        L.setSpacing(8)
        cab = QHBoxLayout()
        cab.setSpacing(8)
        em = QLabel("🎮")
        em.setObjectName("gpuEmoji")
        col = QVBoxLayout()
        col.setSpacing(2)
        self._titulo = QLabel("GPU")
        self._titulo.setObjectName("gpuTit")
        self._sub = QLabel("Detectando…")
        self._sub.setObjectName("gpuSub")
        col.addWidget(self._titulo)
        col.addWidget(self._sub)
        self._temp = QLabel("—")
        self._temp.setObjectName("gpuTemp")
        self._temp.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        cab.addWidget(em, 0)
        cab.addLayout(col, 1)
        cab.addWidget(self._temp, 0)
        L.addLayout(cab)

        fila = QHBoxLayout()
        fila.setSpacing(8)
        col_uso = QVBoxLayout()
        col_uso.setSpacing(2)
        et_uso = QLabel("USO")
        et_uso.setObjectName("gpuChipEt")
        self._bar_uso = QProgressBar()
        self._bar_uso.setObjectName("gpuBar")
        self._bar_uso.setRange(0, 100)
        self._bar_uso.setTextVisible(False)
        self._bar_uso.setFixedHeight(6)
        self._lbl_uso = QLabel("—")
        self._lbl_uso.setObjectName("gpuVal")
        col_uso.addWidget(et_uso)
        col_uso.addWidget(self._bar_uso)
        col_uso.addWidget(self._lbl_uso)

        col_vram = QVBoxLayout()
        col_vram.setSpacing(2)
        et_vram = QLabel("VRAM")
        et_vram.setObjectName("gpuChipEt")
        self._bar_vram = QProgressBar()
        self._bar_vram.setObjectName("gpuBar")
        self._bar_vram.setRange(0, 100)
        self._bar_vram.setTextVisible(False)
        self._bar_vram.setFixedHeight(6)
        self._lbl_vram = QLabel("—")
        self._lbl_vram.setObjectName("gpuVal")
        col_vram.addWidget(et_vram)
        col_vram.addWidget(self._bar_vram)
        col_vram.addWidget(self._lbl_vram)

        fila.addLayout(col_uso, 1)
        fila.addLayout(col_vram, 1)
        L.addLayout(fila)

        self._panel = PanelSerie("GPU %", "%", 0, 100, COLORES_SERIE[3], altura=70)
        L.addWidget(self._panel)
        self._tema: dict[str, str] = {}

    def actualizar(self, info: dict[str, Any] | None) -> None:
        if not info:
            return
        self._titulo.setText(str(info.get("nombre") or "GPU"))
        self._sub.setText(str(info.get("vendor") or ""))
        uso = float(info.get("uso_pct") or 0.0)
        self._bar_uso.setValue(max(0, min(100, int(uso))))
        self._lbl_uso.setText(f"{uso:.0f} %")
        used = float(info.get("vram_used_mb") or 0.0)
        total = float(info.get("vram_total_mb") or 0.0)
        if total > 0:
            pct = max(0.0, min(100.0, used * 100.0 / total))
            self._bar_vram.setValue(int(pct))
            if total >= 1024:
                self._lbl_vram.setText(f"{used / 1024:.1f} / {total / 1024:.1f} GB")
            else:
                self._lbl_vram.setText(f"{used:.0f} / {total:.0f} MB")
        else:
            self._bar_vram.setValue(0)
            self._lbl_vram.setText("—")
        temp = float(info.get("temp_c") or 0.0)
        self._temp.setText(f"{temp:.0f} °C" if temp > 0 else "")
        self._panel.actualizar(uso)

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self._panel.set_color(tema["acento"])
        self._panel.aplicar_texto_tema(tema["mut"], tema["sec"])
        self.setStyleSheet(
            f"""
            QFrame#cardGpu {{
                background-color: {tema["card"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 16px;
            }}
            QLabel#gpuEmoji {{ font-size: 18px; }}
            QLabel#gpuTit {{
                color: {tema["titulo"]};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#gpuSub {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 0.16em;
            }}
            QLabel#gpuTemp {{
                color: {tema["acento"]};
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#gpuChipEt {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.18em;
            }}
            QLabel#gpuVal {{
                color: {tema["titulo"]};
                font-size: 11px;
                font-weight: 700;
            }}
            QProgressBar#gpuBar {{
                background: rgba(255,255,255,0.08);
                border: none;
                border-radius: 3px;
            }}
            QProgressBar#gpuBar::chunk {{
                background-color: {tema["acento"]};
                border-radius: 3px;
            }}
            """
        )


class TarjetaTurbo(QFrame):
    """Tarjeta horizontal con un switch para activar/desactivar Turbo Boost."""

    def __init__(self, on_toggle, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardTurbo")
        self.setAutoFillBackground(False)
        self._on_toggle = on_toggle
        L = QHBoxLayout(self)
        L.setContentsMargins(14, 12, 14, 12)
        L.setSpacing(12)
        em = QLabel("⚡")
        em.setObjectName("turboEmoji")
        col = QVBoxLayout()
        col.setSpacing(2)
        self._titulo = QLabel("Turbo Boost")
        self._titulo.setObjectName("turboTit")
        self._sub = QLabel("Detectando…")
        self._sub.setObjectName("turboSub")
        col.addWidget(self._titulo)
        col.addWidget(self._sub)
        self._estado_lb = QLabel("…")
        self._estado_lb.setObjectName("turboEstado")
        self._estado_lb.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._boton = QPushButton("—")
        self._boton.setObjectName("turboBtn")
        self._boton.setCheckable(True)
        self._boton.setFixedWidth(80)
        self._boton.clicked.connect(self._click)
        L.addWidget(em, 0)
        L.addLayout(col, 1)
        L.addWidget(self._estado_lb, 0)
        L.addWidget(self._boton, 0)
        self._tema: dict[str, str] = {}
        self._estado_actual: bool | None = None
        self._vendor = ""

    def _click(self) -> None:
        if self._estado_actual is None:
            return
        objetivo = not self._estado_actual
        self._boton.setEnabled(False)
        self._boton.setText("…")
        self._on_toggle(objetivo)

    def set_estado(self, info: dict[str, Any] | None) -> None:
        self._boton.setEnabled(True)
        if not info:
            self._sub.setText("No soportado en esta CPU")
            self._estado_lb.setText("—")
            self._boton.setText("—")
            self._boton.setEnabled(False)
            self._estado_actual = None
            self._aplicar_estilo()
            return
        self._vendor = info.get("vendor") or ""
        self._estado_actual = bool(info.get("activo"))
        self._sub.setText(
            f"CPU {self._vendor.upper()} · {info.get('path')}".replace(
                "/sys/devices/system/cpu/", ""
            )
        )
        if self._estado_actual:
            self._estado_lb.setText("ACTIVO")
            self._boton.setText("Desactivar")
            self._boton.setChecked(True)
        else:
            self._estado_lb.setText("INACTIVO")
            self._boton.setText("Activar")
            self._boton.setChecked(False)
        self._aplicar_estilo()

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self._aplicar_estilo()

    def _aplicar_estilo(self) -> None:
        t = self._tema
        if not t:
            return
        ok = self._estado_actual is True
        col_estado = "#22c55e" if ok else (
            "#ef4444" if self._estado_actual is False else t["mut"]
        )
        col_btn = t["acento"] if ok else "rgba(255,255,255,0.18)"
        self.setStyleSheet(
            f"""
            QFrame#cardTurbo {{
                background-color: {t["card"]};
                border: 1px solid {t["card_borde"]};
                border-radius: 14px;
            }}
            QLabel#turboEmoji {{ font-size: 22px; }}
            QLabel#turboTit {{
                color: {t["titulo"]};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#turboSub {{
                color: {t["mut"]};
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 0.06em;
            }}
            QLabel#turboEstado {{
                color: {col_estado};
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.2em;
            }}
            QPushButton#turboBtn {{
                background-color: {col_btn};
                color: white;
                font-size: 11px;
                font-weight: 700;
                border: none;
                border-radius: 14px;
                padding: 6px 10px;
            }}
            QPushButton#turboBtn:disabled {{
                background-color: rgba(255,255,255,0.1);
                color: {t["mut"]};
            }}
            QPushButton#turboBtn:hover {{
                background-color: rgba(255,255,255,0.28);
            }}
            """
        )


class TarjetaApp(QFrame):
    """Fila compacta: nombre · barra CPU · CPU% · RAM · tiempo · matar."""

    def __init__(self, on_matar, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("filaApp")
        self.setAutoFillBackground(False)
        self._on_matar = on_matar
        self._pids: list[int] = []
        L = QHBoxLayout(self)
        L.setContentsMargins(12, 6, 8, 6)
        L.setSpacing(10)
        self._dot = QFrame()
        self._dot.setObjectName("dotApp")
        self._dot.setFixedSize(6, 6)
        self._nb = QLabel("…")
        self._nb.setObjectName("appNombre")
        self._bar = QProgressBar()
        self._bar.setObjectName("appBar")
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)
        self._cpu = QLabel("0 %")
        self._cpu.setObjectName("appCpu")
        self._cpu.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._ram = QLabel("0 MB")
        self._ram.setObjectName("appRam")
        self._ram.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._tiempo = QLabel("0s")
        self._tiempo.setObjectName("appTiempo")
        self._tiempo.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._kill = QPushButton("✕")
        self._kill.setObjectName("appKill")
        self._kill.setFixedSize(20, 20)
        self._kill.setToolTip("Terminar")
        self._kill.clicked.connect(self._click_matar)
        L.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        L.addWidget(self._nb, 0)
        L.addWidget(self._bar, 1)
        L.addWidget(self._cpu, 0)
        L.addWidget(self._ram, 0)
        L.addWidget(self._tiempo, 0)
        L.addWidget(self._kill, 0)
        self._tema: dict[str, str] = {}

    def _click_matar(self) -> None:
        if self._pids and self._on_matar:
            self._on_matar(list(self._pids))

    def actualizar(self, info: dict[str, Any]) -> None:
        nb = (info.get("nombre") or "?")[:22]
        n = int(info.get("n") or 0)
        if n > 1:
            nb = f"{nb} · ×{n}"
        self._nb.setText(nb)
        cpu = float(info.get("cpu_pct") or 0)
        self._cpu.setText(f"{cpu:.0f} %")
        self._bar.setValue(max(0, min(100, int(cpu))))
        self._ram.setText(f"{float(info.get('ram_mb') or 0):.0f} MB")
        self._tiempo.setText(fmt_seg(float(info.get("tiempo_s") or 0)))
        self._pids = list(info.get("pids") or [])

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self.setStyleSheet(
            f"""
            QFrame#filaApp {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
            }}
            QFrame#dotApp {{
                background-color: {tema["acento"]};
                border-radius: 3px;
            }}
            QLabel#appNombre {{
                color: {tema["titulo"]};
                font-size: 11px;
                font-weight: 600;
                min-width: 110px;
            }}
            QLabel#appCpu {{
                color: {tema["sec"]};
                font-size: 11px;
                font-weight: 700;
                min-width: 36px;
            }}
            QLabel#appRam {{
                color: {tema["mut"]};
                font-size: 10px;
                font-weight: 600;
                min-width: 56px;
            }}
            QProgressBar#appBar {{
                border: none;
                background: rgba(255,255,255,0.08);
                border-radius: 2px;
            }}
            QProgressBar#appBar::chunk {{
                background-color: {tema["acento"]};
                border-radius: 2px;
            }}
            QLabel#appTiempo {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 600;
                min-width: 44px;
                letter-spacing: 0.04em;
            }}
            QPushButton#appKill {{
                background: rgba(255,255,255,0.06);
                color: {tema["mut"]};
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 10px;
                font-size: 11px;
                font-weight: 700;
                padding: 0;
            }}
            QPushButton#appKill:hover {{
                background: #ef4444;
                color: white;
                border: none;
            }}
            """
        )


class SeccionColapsable(QWidget):
    """Cabecera con chevron que oculta/muestra el widget de contenido."""

    def __init__(
        self,
        texto: str,
        contenido: QWidget,
        clave: str,
        cfg: dict[str, Any],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(False)
        self._cfg = cfg
        self._clave = clave
        secs = cfg.setdefault("secciones", {})
        self._abierto = bool(secs.get(clave, True))

        self._cab = QFrame()
        self._cab.setObjectName("titSecWrap")
        self._cab.setAutoFillBackground(False)
        self._cab.setCursor(Qt.CursorShape.PointingHandCursor)
        h = QHBoxLayout(self._cab)
        h.setContentsMargins(0, 14, 0, 6)
        h.setSpacing(10)
        self._acc = QFrame()
        self._acc.setObjectName("accentSec")
        self._acc.setFixedSize(4, 18)
        self._chev = QLabel("▾")
        self._chev.setObjectName("chevSec")
        self._lb = QLabel(texto.upper())
        self._lb.setObjectName("titSec")
        h.addWidget(self._acc, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(self._lb, 1, Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(self._chev, 0, Qt.AlignmentFlag.AlignVCenter)
        self._cab.mousePressEvent = self._toggle  # type: ignore[method-assign]

        self._contenido = contenido

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._cab)
        v.addWidget(self._contenido)
        self._aplicar_estado()

    def _toggle(self, _ev=None) -> None:
        self._abierto = not self._abierto
        secs = self._cfg.setdefault("secciones", {})
        secs[self._clave] = self._abierto
        guardar_config(self._cfg)
        self._aplicar_estado()

    def _aplicar_estado(self) -> None:
        self._contenido.setVisible(self._abierto)
        self._chev.setText("▾" if self._abierto else "▸")


def _declinacion_solar(d: datetime) -> float:
    """Declinación solar en grados (aprox., ±0.4°)."""
    n = d.timetuple().tm_yday + d.hour / 24.0
    g = 2 * math.pi / 365.25 * (n - 1)
    return math.degrees(
        0.006918
        - 0.399912 * math.cos(g)
        + 0.070257 * math.sin(g)
        - 0.006758 * math.cos(2 * g)
        + 0.000907 * math.sin(2 * g)
        - 0.002697 * math.cos(3 * g)
        + 0.001480 * math.sin(3 * g)
    )


def _ecuacion_tiempo_min(d: datetime) -> float:
    """Ecuación del tiempo en minutos (corrección reloj solar - reloj civil)."""
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365.25 * (n - 1)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(g)
        - 0.032077 * math.sin(g)
        - 0.014615 * math.cos(2 * g)
        - 0.040849 * math.sin(2 * g)
    )


def _subsolar(d: datetime) -> tuple[float, float]:
    """Lat/Lon en grados del punto subsolar para `d` (UTC)."""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    d_utc = d.astimezone(timezone.utc)
    delta = _declinacion_solar(d_utc)
    eot = _ecuacion_tiempo_min(d_utc)
    horas_utc = d_utc.hour + d_utc.minute / 60.0 + d_utc.second / 3600.0
    lon_sol = -15.0 * (horas_utc - 12.0 + eot / 60.0)
    while lon_sol > 180:
        lon_sol -= 360
    while lon_sol < -180:
        lon_sol += 360
    return delta, lon_sol


class MapaSol(QWidget):
    """Mapa mundi minimalista (rejilla + terminador) con la zona iluminada."""

    def __init__(self, lat_obs: float, lon_obs: float, parent=None) -> None:
        super().__init__(parent)
        self._lat = float(lat_obs)
        self._lon = float(lon_obs)
        self.setMinimumHeight(140)
        self.setMaximumHeight(180)
        self._tema: dict[str, str] = {}
        self._t_redibujo = QTimer(self)
        self._t_redibujo.timeout.connect(self.update)
        self._t_redibujo.start(60_000)

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self.update()

    def _proy(self, lat: float, lon: float, w: int, h: int) -> QPointF:
        x = (lon + 180.0) / 360.0 * w
        y = (90.0 - lat) / 180.0 * h
        return QPointF(x, y)

    def paintEvent(self, _e) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = self.height()
        ahora = datetime.now(timezone.utc)
        delta, lon_sol = _subsolar(ahora)

        rect = QRectF(0, 0, w, h)
        path_round = QPainterPath()
        path_round.addRoundedRect(rect, 14, 14)
        p.setClipPath(path_round)

        # Fondo: océanos en azul nocturno
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(10, 22, 48))
        bg.setColorAt(1.0, QColor(4, 10, 26))
        p.fillRect(rect, bg)

        # Rejilla muy sutil
        rejilla = QPen(QColor(255, 255, 255, 18), 1)
        rejilla.setCosmetic(True)
        p.setPen(rejilla)
        for lat in (-60, -30, 0, 30, 60):
            y = (90.0 - lat) / 180.0 * h
            p.drawLine(QPointF(0, y), QPointF(w, y))
        for lon in (-120, -60, 0, 60, 120):
            x = (lon + 180.0) / 360.0 * w
            p.drawLine(QPointF(x, 0), QPointF(x, h))

        # Continentes - rellenos con color base "noche"
        continentes_path = QPainterPath()
        for poly in CONTINENTES:
            if not poly:
                continue
            primer = self._proy(poly[0][1], poly[0][0], w, h)
            sub = QPainterPath()
            sub.moveTo(primer)
            for lon, lat in poly[1:]:
                sub.lineTo(self._proy(lat, lon, w, h))
            sub.closeSubpath()
            continentes_path.addPath(sub)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(continentes_path, QColor(30, 50, 80))

        # Calcular zona de día (terminador)
        delta_rad = math.radians(delta)
        polo_norte_iluminado = delta >= 0
        camino_dia = QPainterPath()
        if polo_norte_iluminado:
            camino_dia.moveTo(0, 0)
        else:
            camino_dia.moveTo(0, h)
        pasos = max(96, w // 2)
        puntos_term: list[QPointF] = []
        for i in range(pasos + 1):
            x = i / pasos * w
            lon = -180.0 + 360.0 * (x / w)
            if abs(math.tan(delta_rad)) < 1e-6:
                lat_t = 0.0
            else:
                arg = -math.cos(math.radians(lon - lon_sol)) / math.tan(delta_rad)
                arg = max(-1.0, min(1.0, arg))
                lat_t = math.degrees(math.atan(arg))
            pt = self._proy(lat_t, lon, w, h)
            puntos_term.append(pt)
            camino_dia.lineTo(pt.x(), pt.y())
        if polo_norte_iluminado:
            camino_dia.lineTo(w, 0)
        else:
            camino_dia.lineTo(w, h)
        camino_dia.closeSubpath()

        # Pintamos los continentes iluminados (intersección con la zona diurna)
        continentes_dia = continentes_path.intersected(camino_dia)
        p.fillPath(continentes_dia, QColor(120, 165, 90))

        # Wash dorado encima de la zona iluminada para sensación de "día"
        dia_grad = QLinearGradient(0, 0, 0, h)
        dia_grad.setColorAt(0.0, QColor(255, 220, 140, 32))
        dia_grad.setColorAt(1.0, QColor(255, 170, 80, 22))
        p.fillPath(camino_dia, QBrush(dia_grad))

        # Contornos de los continentes encima
        contorno = QPen(QColor(255, 255, 255, 60), 1)
        contorno.setCosmetic(True)
        p.setPen(contorno)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(continentes_path)

        # Halo del subsolar
        x_sol = (lon_sol + 180.0) / 360.0 * w
        y_sol = (90.0 - delta) / 180.0 * h
        radio_halo = max(40, min(w, h * 2) // 4)
        halo = QRadialGradient(QPointF(x_sol, y_sol), radio_halo)
        halo.setColorAt(0.0, QColor(255, 220, 150, 90))
        halo.setColorAt(0.6, QColor(255, 200, 120, 24))
        halo.setColorAt(1.0, QColor(255, 200, 120, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(x_sol, y_sol), radio_halo, radio_halo)

        # Línea del terminador
        terminador = QPen(QColor(255, 220, 150, 160), 1.4)
        terminador.setCosmetic(True)
        p.setPen(terminador)
        prev: QPointF | None = None
        for pt in puntos_term:
            if prev is not None:
                p.drawLine(prev, pt)
            prev = pt

        # Sol
        p.setBrush(QColor(255, 235, 180))
        p.setPen(QPen(QColor(255, 255, 255, 220), 1))
        p.drawEllipse(QPointF(x_sol, y_sol), 3.2, 3.2)

        # Punto del observador
        pt_obs = self._proy(self._lat, self._lon, w, h)
        ac = QColor(self._tema.get("acento", "#22d3ee"))
        glow = QRadialGradient(pt_obs, 10.0)
        glow.setColorAt(0.0, QColor(ac.red(), ac.green(), ac.blue(), 220))
        glow.setColorAt(1.0, QColor(ac.red(), ac.green(), ac.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(pt_obs, 10, 10)
        p.setBrush(ac)
        p.setPen(QPen(QColor(255, 255, 255, 240), 1))
        p.drawEllipse(pt_obs, 3.0, 3.0)

        # Marco
        p.setPen(QPen(QColor(255, 255, 255, 32), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

        p.end()


class TarjetaCita(QFrame):
    """Pensamiento del día (autor + año), determinista por fecha."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardCita")
        self.setAutoFillBackground(False)
        L = QHBoxLayout(self)
        L.setContentsMargins(14, 12, 14, 12)
        L.setSpacing(10)
        self._comilla = QLabel("“")
        self._comilla.setObjectName("citaComilla")
        self._comilla.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        col = QVBoxLayout()
        col.setSpacing(4)
        self._texto = QLabel("…")
        self._texto.setObjectName("citaTexto")
        self._texto.setWordWrap(True)
        self._autor = QLabel("—")
        self._autor.setObjectName("citaAutor")
        col.addWidget(self._texto)
        col.addWidget(self._autor)
        L.addWidget(self._comilla, 0, Qt.AlignmentFlag.AlignTop)
        L.addLayout(col, 1)
        self._tema: dict[str, str] = {}
        self.refrescar()

    def refrescar(self) -> None:
        c = cita_del_dia()
        self._texto.setText(c["texto"])
        self._autor.setText(f"— {c['autor']} · {c['anyo']}")

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self.setStyleSheet(
            f"""
            QFrame#cardCita {{
                background-color: {tema["card"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 14px;
            }}
            QLabel#citaComilla {{
                color: {tema["acento"]};
                font-family: "Georgia","Times New Roman",serif;
                font-size: 32px;
                font-weight: 700;
                margin-top: -4px;
            }}
            QLabel#citaTexto {{
                color: {tema["titulo"]};
                font-size: 12px;
                font-weight: 500;
                font-style: italic;
                line-height: 140%;
            }}
            QLabel#citaAutor {{
                color: {tema["mut"]};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.06em;
            }}
            """
        )


class TarjetaFan(QFrame):
    """ASUS Fan Mode: Silencioso · Normal · Overboost."""

    MODOS = (
        (2, "Silencioso", "🌙"),
        (0, "Normal", "💨"),
        (1, "Overboost", "🚀"),
    )

    def __init__(self, on_set, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardFan")
        self.setAutoFillBackground(False)
        self._on_set = on_set
        self._modo_actual: int | None = None
        self._botones: dict[int, QPushButton] = {}

        L = QVBoxLayout(self)
        L.setContentsMargins(14, 12, 14, 12)
        L.setSpacing(8)

        cab = QHBoxLayout()
        cab.setSpacing(8)
        em = QLabel("🪭")
        em.setObjectName("fanEmoji")
        col = QVBoxLayout()
        col.setSpacing(2)
        self._titulo = QLabel("Modo de ventilador")
        self._titulo.setObjectName("fanTit")
        self._sub = QLabel("Detectando…")
        self._sub.setObjectName("fanSub")
        col.addWidget(self._titulo)
        col.addWidget(self._sub)
        cab.addWidget(em, 0)
        cab.addLayout(col, 1)
        L.addLayout(cab)

        fila = QHBoxLayout()
        fila.setSpacing(6)
        for valor, etiqueta, emoji in self.MODOS:
            b = QPushButton(f"{emoji}  {etiqueta}")
            b.setObjectName("fanBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, v=valor: self._click(v))
            fila.addWidget(b, 1)
            self._botones[valor] = b
        L.addLayout(fila)
        self._tema: dict[str, str] = {}

    def _click(self, valor: int) -> None:
        for b in self._botones.values():
            b.setEnabled(False)
        self._on_set(valor)

    def set_estado(self, info: dict[str, Any] | None) -> None:
        for b in self._botones.values():
            b.setEnabled(True)
        if not info:
            self._sub.setText("ASUS WMI / platform_profile no disponible")
            for b in self._botones.values():
                b.setChecked(False)
                b.setEnabled(False)
            self._modo_actual = None
            return
        self._modo_actual = int(info.get("valor", 0))
        nombre = info.get("nombre", "?")
        detalle = info.get("detalle", "")
        fuente = info.get("fuente", "")
        rutas = info.get("rutas") or []
        partes = [f"Activo: {nombre}"]
        if detalle and detalle.lower() != nombre.lower():
            partes.append(f"sysfs: {detalle}")
        if fuente:
            partes.append(f"vía {fuente}")
        if len(rutas) > 1:
            partes.append("(2 interfaces detectadas)")
        self._sub.setText(" · ".join(partes))
        self._sub.setToolTip(
            "Interfaces detectadas:\n  - "
            + "\n  - ".join(rutas)
            + (
                f"\nOpciones del platform_profile: {' / '.join(info.get('choices', []))}"
                if info.get("choices")
                else ""
            )
        )
        for v, b in self._botones.items():
            b.setChecked(v == self._modo_actual)
        self._aplicar_estilo()

    def set_resultado(self, ok: bool, mensaje: str) -> None:
        if ok:
            self._sub.setText(f"✓ {mensaje}")
        else:
            self._sub.setText(f"⚠ {mensaje}")
        self._sub.setToolTip(mensaje)

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self._aplicar_estilo()

    def _aplicar_estilo(self) -> None:
        t = self._tema
        if not t:
            return
        self.setStyleSheet(
            f"""
            QFrame#cardFan {{
                background-color: {t["card"]};
                border: 1px solid {t["card_borde"]};
                border-radius: 16px;
            }}
            QLabel#fanEmoji {{ font-size: 18px; }}
            QLabel#fanTit {{
                color: {t["titulo"]};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#fanSub {{
                color: {t["mut"]};
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.04em;
            }}
            QPushButton#fanBtn {{
                background: rgba(255,255,255,0.05);
                color: {t["sec"]};
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                padding: 6px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#fanBtn:hover {{
                background: rgba(255,255,255,0.10);
            }}
            QPushButton#fanBtn:checked {{
                background-color: {t["acento"]};
                color: white;
                border: none;
                font-weight: 700;
            }}
            QPushButton#fanBtn:disabled {{
                color: rgba(255,255,255,0.3);
            }}
            """
        )


class GestorAlertasTermicas:
    """Decide cuándo notificar problemas térmicos con histéresis.

    Reglas:
    - Notifica cuando un sensor cruza WARN → estado_actual = warn
    - Notifica cuando cruza CRIT → estado_actual = crit (incluso si ya estaba en warn)
    - Limpia el estado cuando baja `histeresis` °C por debajo del umbral cruzado.
    - Cooldown mínimo entre notificaciones del mismo sensor: `cooldown_s`.
    """

    def __init__(
        self,
        *,
        histeresis: float = 3.0,
        cooldown_s: float = 5 * 60.0,
        cb_notificar=None,
    ) -> None:
        self.histeresis = histeresis
        self.cooldown_s = cooldown_s
        self._cb = cb_notificar
        self._estado: dict[str, str] = {}
        self._ultima: dict[str, float] = {}
        self.silenciado: bool = False

    def evaluar(self, items: list[tuple[str, float]]) -> list[dict[str, Any]]:
        ahora = time.time()
        alertas_ahora: list[dict[str, Any]] = []
        actuales: dict[str, dict[str, Any]] = {}
        for nombre, valor in items:
            try:
                v = float(valor)
            except (TypeError, ValueError):
                continue
            warn, crit = umbrales_temperatura(nombre)
            actuales[nombre] = {"valor": v, "warn": warn, "crit": crit}

        for nombre, d in actuales.items():
            v = d["valor"]
            warn = d["warn"]
            crit = d["crit"]
            previo = self._estado.get(nombre)
            nuevo: str | None = None
            if v >= crit:
                nuevo = "crit"
            elif v >= warn:
                nuevo = "warn"
            else:
                if previo == "warn" and v < warn - self.histeresis:
                    nuevo = None
                elif previo == "crit" and v < crit - self.histeresis:
                    nuevo = "warn" if v >= warn else None
                else:
                    nuevo = previo

            transicion_warn = nuevo == "warn" and previo not in ("warn", "crit")
            escalada_crit = nuevo == "crit" and previo != "crit"
            transicion_arriba = transicion_warn or escalada_crit
            ultima = self._ultima.get(nombre, 0.0)
            cooldown_ok = (ahora - ultima) > self.cooldown_s
            puede_notificar = (
                transicion_arriba
                and not self.silenciado
                and (escalada_crit or cooldown_ok)
            )
            if nuevo:
                alertas_ahora.append(
                    {
                        "nombre": nombre,
                        "valor": v,
                        "warn": warn,
                        "crit": crit,
                        "nivel": nuevo,
                    }
                )
            if puede_notificar and self._cb is not None:
                self._cb(nombre, v, nuevo, crit if nuevo == "crit" else warn)
                self._ultima[nombre] = ahora
            if nuevo is None:
                self._estado.pop(nombre, None)
            else:
                self._estado[nombre] = nuevo

        for nb in list(self._estado.keys()):
            if nb not in actuales:
                self._estado.pop(nb, None)

        alertas_ahora.sort(
            key=lambda a: (-({"crit": 2, "warn": 1}.get(a["nivel"], 0)), -a["valor"])
        )
        return alertas_ahora


class DialogoPartido(QDialog):
    """Detalle del último y próximo partido del equipo seleccionado.

    Refresco automático cada 30s mientras el diálogo esté abierto, lo que
    permite ver el marcador en tiempo real cuando un partido está en juego.
    """

    EN_DIRECTO = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "in play", "in progress", "live"}

    def __init__(self, datos: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(datos.get("titulo") or "Partido")
        self.setModal(False)
        self.setMinimumWidth(420)
        self._datos = dict(datos or {})
        self._sig_actualizar = pyqtSignal  # noqa: F841
        self._tema = (
            parent._tema_actual if parent is not None and hasattr(parent, "_tema_actual") else {}
        )

        L = QVBoxLayout(self)
        L.setContentsMargins(18, 16, 18, 16)
        L.setSpacing(12)

        cab = QHBoxLayout()
        cab.setSpacing(10)
        self._em = QLabel(datos.get("emoji") or "🏆")
        self._em.setStyleSheet("font-size: 22px;")
        col = QVBoxLayout()
        col.setSpacing(2)
        self._tit = QLabel(datos.get("titulo") or "—")
        self._tit.setObjectName("dlgTit")
        self._sub = QLabel(datos.get("liga") or "")
        self._sub.setObjectName("dlgSub")
        col.addWidget(self._tit)
        col.addWidget(self._sub)
        cab.addWidget(self._em, 0, Qt.AlignmentFlag.AlignVCenter)
        cab.addLayout(col, 1)
        L.addLayout(cab)

        self._caja_prev = self._construir_caja("ÚLTIMO PARTIDO", L)
        self._caja_next = self._construir_caja("PRÓXIMO PARTIDO", L)

        # estado
        self._estado_lbl = QLabel("")
        self._estado_lbl.setObjectName("dlgEstado")
        self._estado_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        L.addWidget(self._estado_lbl)

        # botón cerrar
        from PyQt6.QtWidgets import QPushButton

        h = QHBoxLayout()
        h.addStretch(1)
        self._btn_refrescar = QPushButton("Refrescar")
        self._btn_refrescar.clicked.connect(self._refrescar_ahora)
        h.addWidget(self._btn_refrescar)
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.accept)
        h.addWidget(btn_cerrar)
        L.addLayout(h)

        self._aplicar_estilos()
        self._render(self._datos)

        # Timer de refresco
        self._t = QTimer(self)
        self._t.timeout.connect(self._refrescar_async)
        self._t.start(30_000)

    def _construir_caja(self, etiqueta: str, padre: QVBoxLayout) -> dict[str, QLabel]:
        wrap = QFrame()
        wrap.setObjectName("dlgCaja")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(6)
        et = QLabel(etiqueta)
        et.setObjectName("dlgEtiqueta")
        v.addWidget(et)

        # equipos + marcador
        fila = QHBoxLayout()
        fila.setSpacing(10)
        home = QLabel("—")
        home.setObjectName("dlgEquipo")
        home.setWordWrap(True)
        score = QLabel("·")
        score.setObjectName("dlgMarcador")
        score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score.setMinimumWidth(80)
        away = QLabel("—")
        away.setObjectName("dlgEquipo")
        away.setWordWrap(True)
        away.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        fila.addWidget(home, 1)
        fila.addWidget(score, 0)
        fila.addWidget(away, 1)
        v.addLayout(fila)

        meta = QLabel("")
        meta.setObjectName("dlgMeta")
        meta.setWordWrap(True)
        v.addWidget(meta)

        sede = QLabel("")
        sede.setObjectName("dlgSede")
        sede.setWordWrap(True)
        v.addWidget(sede)

        padre.addWidget(wrap)
        return {"home": home, "away": away, "score": score, "meta": meta, "sede": sede}

    def _aplicar_estilos(self) -> None:
        t = self._tema or {
            "card": "#0b1220",
            "card_borde": "rgba(255,255,255,0.08)",
            "titulo": "#f8fafc",
            "sec": "#cbd5e1",
            "mut": "rgba(255,255,255,0.55)",
            "acento": "#60a5fa",
        }
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {t['card']};
                color: {t['titulo']};
            }}
            QFrame#dlgCaja {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {t['card_borde']};
                border-radius: 12px;
            }}
            QLabel#dlgTit {{
                color: {t['titulo']};
                font-size: 16px;
                font-weight: 800;
                letter-spacing: 0.04em;
            }}
            QLabel#dlgSub {{
                color: {t['sec']};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#dlgEtiqueta {{
                color: {t['mut']};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.18em;
            }}
            QLabel#dlgEquipo {{
                color: {t['titulo']};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#dlgMarcador {{
                color: {t['acento']};
                font-size: 22px;
                font-weight: 800;
                letter-spacing: 0.05em;
            }}
            QLabel#dlgMeta {{
                color: {t['sec']};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#dlgSede {{
                color: {t['mut']};
                font-size: 10px;
            }}
            QLabel#dlgEstado {{
                color: {t['mut']};
                font-size: 10px;
                font-style: italic;
            }}
            QPushButton {{
                background-color: rgba(255,255,255,0.08);
                color: {t['titulo']};
                border: 1px solid {t['card_borde']};
                padding: 6px 14px;
                border-radius: 8px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: rgba(255,255,255,0.14); }}
            """
        )

    def _render(self, d: dict[str, Any]) -> None:
        if d.get("titulo"):
            self._tit.setText(d["titulo"])
        if d.get("emoji"):
            self._em.setText(d["emoji"])
        if d.get("liga"):
            self._sub.setText(d["liga"])

        if d.get("err"):
            self._caja_prev["meta"].setText(str(d["err"]))
            return

        prev = d.get("prev") or {}
        nxt = d.get("next") or {}

        self._render_caja(self._caja_prev, prev, terminado=True)
        self._render_caja(self._caja_next, nxt, terminado=False)

        # estado / podio F1
        if d.get("podio"):
            podio = d["podio"]
            txt = " · ".join(
                f"{p['pos']}º {p['apellido']} ({p['equipo']})" for p in podio
            )
            self._estado_lbl.setText("Podio: " + txt)
        else:
            estado_actual = self._estado_actual(prev, nxt)
            self._estado_lbl.setText(estado_actual)

    def _render_caja(
        self, caja: dict[str, QLabel], p: dict[str, Any], *, terminado: bool
    ) -> None:
        if not p:
            caja["home"].setText("Sin datos")
            caja["away"].setText("")
            caja["score"].setText("·")
            caja["meta"].setText("")
            caja["sede"].setText("")
            return
        caja["home"].setText(str(p.get("home_full") or p.get("home") or "—"))
        caja["away"].setText(str(p.get("away_full") or p.get("away") or "—"))
        sh = p.get("score_home")
        sa = p.get("score_away")
        if sh is not None and sa is not None:
            caja["score"].setText(f"{sh}  -  {sa}")
        else:
            caja["score"].setText(p.get("estado", "·"))
        meta = []
        if p.get("fecha"):
            meta.append(p["fecha"])
        if p.get("ronda"):
            meta.append(f"Jornada {p['ronda']}")
        if p.get("estado_raw"):
            meta.append(p["estado_raw"])
        if p.get("tv"):
            meta.append(f"TV: {p['tv']}")
        caja["meta"].setText(" · ".join(meta))
        sede = []
        if p.get("sede"):
            sede.append(p["sede"])
        if p.get("ciudad"):
            sede.append(p["ciudad"])
        caja["sede"].setText(" · ".join(sede))

    def _estado_actual(self, prev: dict[str, Any], nxt: dict[str, Any]) -> str:
        # Detectar si hay partido en curso
        for ev in (prev, nxt):
            estado = (ev.get("estado_raw") or "").strip()
            if any(s.lower() == estado.lower() for s in self.EN_DIRECTO) or any(
                k.lower() in estado.lower() for k in ("live", "play", "1st", "2nd", "3rd", "4th", "min")
            ):
                return f"⏱  PARTIDO EN CURSO · {estado}"
        if nxt and nxt.get("dt_utc"):
            try:
                dt = datetime.fromisoformat(nxt["dt_utc"])
                ahora = datetime.now(timezone.utc)
                delta = (dt - ahora).total_seconds()
                if -1800 <= delta <= 1800:
                    return "⏱  EMPIEZA AHORA"
                if 0 < delta <= 24 * 3600:
                    horas = int(delta / 3600)
                    mins = int((delta % 3600) / 60)
                    return f"Próximo partido en {horas}h {mins}m"
            except (ValueError, TypeError):
                pass
        return "Refresco automático cada 30s"

    def _refrescar_ahora(self) -> None:
        self._refrescar_async()

    def _refrescar_async(self) -> None:
        # Enriquecer último y próximo con lookupevent si tienen ID (sólo TSD)
        ids = []
        for k in ("prev", "next"):
            ev = (self._datos.get(k) or {})
            if ev.get("id"):
                ids.append((k, ev["id"]))

        is_f1 = bool(self._datos.get("next", {}).get("es_f1") or self._datos.get("prev", {}).get("es_f1"))

        def trabajo() -> None:
            d_actualizado = dict(self._datos)
            if is_f1:
                try:
                    nuevo = traer_f1()
                    if not nuevo.get("err"):
                        d_actualizado.update(
                            {k: nuevo.get(k) for k in ("prev", "next") if nuevo.get(k)}
                        )
                except Exception:  # noqa: BLE001
                    pass
            else:
                # equipo TSD: re-pedimos detalle de cada evento por id
                for k, idv in ids:
                    try:
                        upd = lookup_evento_tsd(idv)
                        if upd:
                            d_actualizado[k] = upd
                    except Exception:  # noqa: BLE001
                        pass
            # señal segura UI
            self._datos = d_actualizado
            QTimer.singleShot(0, lambda: self._render(self._datos))

        threading.Thread(target=trabajo, daemon=True).start()

    def closeEvent(self, e) -> None:  # type: ignore[override]
        self._t.stop()
        super().closeEvent(e)


class DialogoEquipos(QDialog):
    """Editor: añade, quita y reordena los equipos a seguir en la sección Resultados."""

    LIGAS_OPCIONES: list[tuple[str, str]] = [
        ("laliga", "La Liga ⚽"),
        ("champions", "Champions ⚽"),
        ("bundesliga", "Bundesliga ⚽"),
        ("premier", "Premier League ⚽"),
        ("nba", "NBA 🏀"),
        ("mlb", "MLB ⚾"),
        ("f1", "Fórmula 1 🏎️"),
    ]

    def __init__(self, equipos: list[dict[str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Equipos a seguir")
        self.setMinimumWidth(420)
        self._equipos = [dict(e) for e in equipos]

        L = QVBoxLayout(self)
        L.setContentsMargins(14, 14, 14, 14)
        L.setSpacing(8)

        info = QLabel(
            "Añade tus equipos. Usa el nombre completo en inglés cuando sea posible "
            "(ej. 'Real Madrid', 'Bayern Munich', 'Los Angeles Lakers').\n"
            "Para Fórmula 1, basta con elegir 'Fórmula 1' (no necesita equipo)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 11px;")
        L.addWidget(info)

        self._lista = QListWidget()
        self._lista.setStyleSheet(
            "QListWidget { background: rgba(255,255,255,0.05); "
            "border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; "
            "color: white; padding: 4px; }"
            "QListWidget::item { padding: 6px; border-radius: 4px; }"
            "QListWidget::item:selected { background: rgba(34,211,238,0.35); }"
        )
        L.addWidget(self._lista, 1)
        self._refrescar_lista()

        fila_add = QHBoxLayout()
        self._cb_liga = QComboBox()
        for clave, etiqueta in self.LIGAS_OPCIONES:
            self._cb_liga.addItem(etiqueta, clave)
        self._ed_nombre = QLineEdit()
        self._ed_nombre.setPlaceholderText("Nombre del equipo (vacío para F1)")
        btn_add = QPushButton("➕ Añadir")
        btn_add.clicked.connect(self._add)
        fila_add.addWidget(self._cb_liga, 1)
        fila_add.addWidget(self._ed_nombre, 2)
        fila_add.addWidget(btn_add, 0)
        L.addLayout(fila_add)

        fila_btns = QHBoxLayout()
        btn_up = QPushButton("▲ Subir")
        btn_dn = QPushButton("▼ Bajar")
        btn_rm = QPushButton("✕ Quitar")
        btn_up.clicked.connect(lambda: self._mover(-1))
        btn_dn.clicked.connect(lambda: self._mover(+1))
        btn_rm.clicked.connect(self._quitar)
        for b in (btn_up, btn_dn, btn_rm):
            b.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.06); color: white; "
                "border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; "
                "padding: 6px 10px; font-size: 11px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.12); }"
            )
        fila_btns.addWidget(btn_up)
        fila_btns.addWidget(btn_dn)
        fila_btns.addWidget(btn_rm)
        fila_btns.addStretch(1)
        L.addLayout(fila_btns)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        L.addWidget(botones)

        self.setStyleSheet(
            "QDialog { background-color: #1f2937; color: white; }"
            "QLineEdit, QComboBox { background: rgba(255,255,255,0.06); "
            "color: white; border: 1px solid rgba(255,255,255,0.15); "
            "border-radius: 6px; padding: 6px 8px; }"
            "QPushButton { background: rgba(34,211,238,0.85); color: black; "
            "border: none; border-radius: 8px; padding: 6px 12px; font-weight: 700; }"
            "QPushButton:hover { background: rgba(34,211,238,1.0); }"
        )

    def _refrescar_lista(self) -> None:
        self._lista.clear()
        for eq in self._equipos:
            liga = eq.get("liga", "")
            etiqueta_liga = next(
                (e for c, e in self.LIGAS_OPCIONES if c == liga), liga
            )
            nb = eq.get("nombre", "") or "(toda la liga)"
            it = QListWidgetItem(f"{etiqueta_liga}   ·   {nb}")
            self._lista.addItem(it)

    def _add(self) -> None:
        liga = self._cb_liga.currentData()
        nombre = self._ed_nombre.text().strip()
        if liga != "f1" and not nombre:
            return
        if liga == "f1":
            self._equipos.append({"liga": "f1"})
        else:
            self._equipos.append({"liga": liga, "nombre": nombre})
        self._ed_nombre.clear()
        self._refrescar_lista()

    def _quitar(self) -> None:
        i = self._lista.currentRow()
        if 0 <= i < len(self._equipos):
            self._equipos.pop(i)
            self._refrescar_lista()

    def _mover(self, delta: int) -> None:
        i = self._lista.currentRow()
        j = i + delta
        if 0 <= i < len(self._equipos) and 0 <= j < len(self._equipos):
            self._equipos[i], self._equipos[j] = self._equipos[j], self._equipos[i]
            self._refrescar_lista()
            self._lista.setCurrentRow(j)

    def equipos(self) -> list[dict[str, str]]:
        return self._equipos


class Ventana(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Clima · Sistema · Deportes")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._abrir_menu)

        self._cfg = cargar_config()
        self._sig = Senales()
        self._sig.clima.connect(self._pintar_clima)
        self._sig.deportes.connect(self._aplicar_deportes)
        self._sig.alertas.connect(self._aplicar_alertas)

        self._tema_actual: dict[str, str] = tema_visual(3, True)
        self._tarj_baterias: dict[str, TarjetaBateria] = {}
        self._ultimos_datos_clima: dict[str, Any] = {}
        self._gestor_temp = GestorAlertasTermicas(
            cb_notificar=self._notificar_temp_handler
        )
        self._gestor_temp.silenciado = bool(self._cfg.get("silenciar_temp", False))
        self._monitor_red = MonitorRed()
        self._monitor_apps = MonitorApps()
        self._filas_apps: list[TarjetaApp] = []
        self._filas_docker: list[TarjetaDocker] = []

        self._construir_ui()
        self._sig.descarga_progreso.connect(self._on_descarga_progreso)
        self._sig.descarga_fin.connect(self._on_descarga_fin)
        self._sig.noticias.connect(self._aplicar_noticias)
        self._modo_claro = bool(self._cfg.get("modo_claro", False))
        self._auto_ocultar = bool(self._cfg.get("auto_ocultar", False))
        self._opacidad_base = float(self._cfg.get("opacidad", 1.0))
        self.setMinimumSize(self.MIN_W, self.MIN_H)
        ancho_guardado = int(self._cfg.get("ancho", 0))
        alto_guardado = int(self._cfg.get("alto", 0))
        if ancho_guardado >= self.MIN_W and alto_guardado >= self.MIN_H:
            self.resize(ancho_guardado, alto_guardado)
        else:
            self._aplicar_tamano(self._cfg.get("tamano", "normal"))
        self._aplicar_capa(self._cfg.get("capa", "normal"))
        self._aplicar_anclaje(self._cfg.get("anclaje", "libre"))
        self._resize_modo: str | None = None
        self._resize_origen: tuple[int, int, int, int] | None = None

        self.setWindowOpacity(max(0.3, min(1.0, self._opacidad_base)))
        self.setMouseTracking(True)
        self._marco.setMouseTracking(True)

        self._aplicar_tema(tema_visual(3, True, claro_forzado=self._modo_claro))

        # Activar autostart la primera vez: si no se ha decidido aún en cfg
        if "autostart" not in self._cfg:
            lanzador = autostart.ruta_lanzador_por_defecto(Path(__file__).resolve().parent)
            ok, _ = autostart.activar(str(lanzador))
            self._cfg["autostart"] = bool(ok)
            guardar_config(self._cfg)

        self._t_clima = QTimer(self)
        self._t_clima.timeout.connect(self._pedir_clima)
        self._t_clima.start(300_000)
        self._pedir_clima()

        self._t_sys = QTimer(self)
        self._t_sys.timeout.connect(self._tick_sistema)
        self._t_sys.start(1_000)
        self._tick_sistema()

        self._t_deportes = QTimer(self)
        self._t_deportes.timeout.connect(self._pedir_deportes)
        self._t_deportes.start(15 * 60_000)
        self._pedir_deportes()

        self._t_bat = QTimer(self)
        self._t_bat.timeout.connect(self._tick_baterias)
        self._t_bat.start(30_000)
        self._tick_baterias()

        self._t_red = QTimer(self)
        self._t_red.timeout.connect(self._tick_red)
        self._t_red.start(2_000)
        self._tick_red()

        self._t_apps = QTimer(self)
        self._t_apps.timeout.connect(self._tick_apps)
        self._t_apps.start(2_000)
        self._tick_apps()

        self._docker_stats_cache: dict[str, Any] = {}
        self._t_docker = QTimer(self)
        self._t_docker.timeout.connect(self._tick_docker)
        self._t_docker.start(4_000)
        self._tick_docker()
        self._t_docker_stats = QTimer(self)
        self._t_docker_stats.timeout.connect(self._refrescar_docker_stats)
        self._t_docker_stats.start(6_000)
        self._refrescar_docker_stats()

        self._t_ping = QTimer(self)
        self._t_ping.timeout.connect(self._refrescar_ping)
        self._t_ping.start(5_000)
        self._refrescar_ping()

        self._t_ippub = QTimer(self)
        self._t_ippub.timeout.connect(self._refrescar_ip_publica)
        self._t_ippub.start(300_000)
        self._refrescar_ip_publica()

        self._t_fan = QTimer(self)
        self._t_fan.timeout.connect(self._tick_fan)
        self._t_fan.start(5_000)
        self._tick_fan()

        self._t_cita = QTimer(self)
        self._t_cita.timeout.connect(self._tick_cita)
        self._t_cita.start(60 * 60_000)

        self._t_alertas = QTimer(self)
        self._t_alertas.timeout.connect(self._pedir_alertas)
        self._t_alertas.start(15 * 60_000)
        self._pedir_alertas()

        self._t_solar = QTimer(self)
        self._t_solar.timeout.connect(self._tick_solar)
        self._t_solar.start(10 * 60_000)

        self._t_noticias = QTimer(self)
        self._t_noticias.timeout.connect(self._pedir_noticias)
        self._t_noticias.start(20 * 60_000)
        self._pedir_noticias()

        self._t_turbo = QTimer(self)
        self._t_turbo.timeout.connect(self._tick_turbo)
        self._t_turbo.start(5_000)
        self._tick_turbo()

    # ---------- UI ----------
    def _construir_ui(self) -> None:
        self._panel_clima = PanelClima()
        self._panel_dep = PanelDeportes(
            self._equipos_config,
            self._abrir_dialogo_partido,
        )
        self._sec_resultados = SeccionColapsable(
            "Resultados", self._panel_dep, "resultados", self._cfg
        )
        self._panel_desc = PanelDescargas(
            self._cfg,
            Path(
                self._cfg.get("descargas_carpeta")
                or str(carpeta_descargas_por_defecto())
            ),
        )
        self._panel_desc.btn_carpeta.clicked.connect(self._elegir_carpeta_descarga)
        self._panel_desc.btn_descargar.clicked.connect(self._iniciar_descarga)
        self._sec_descargas = SeccionColapsable(
            "Descargas",
            self._panel_desc,
            "descargas",
            self._cfg,
        )
        self._panel_noticias = PanelNoticiasFeed(self._pedir_noticias)
        self._sec_noticias = SeccionColapsable(
            "Noticias · última hora",
            self._panel_noticias,
            "noticias",
            self._cfg,
        )
        self._panel_metricas = PanelMetricasEquipo()
        self._panel_cpu = self._panel_metricas.panel_cpu
        self._panel_ram = self._panel_metricas.panel_ram
        self._panel_disk = self._panel_metricas.panel_disk
        self._lbl_freq = self._panel_metricas.lbl_freq
        self._sec_tu_equipo = SeccionColapsable(
            "Tu equipo", self._panel_metricas, "tu_equipo", self._cfg
        )
        self._panel_solar = PanelSolarDashboard(self._mostrar_planeta)
        self._mapa_solar = self._panel_solar.mapa_solar
        self._panel_planeta = self._panel_solar.panel_planeta
        self._sec_solar = SeccionColapsable(
            "Sistema Solar",
            self._panel_solar,
            "solar",
            self._cfg,
        )
        self._tarj_gpu = TarjetaGpu()
        self._sec_gpu = SeccionColapsable(
            "GPU", self._tarj_gpu, "gpu", self._cfg
        )
        self._sec_gpu.hide()
        self._tarj_turbo = TarjetaTurbo(self._toggle_turbo)
        self._sec_turbo = SeccionColapsable(
            "Turbo Boost", self._tarj_turbo, "turbo", self._cfg
        )
        self._sec_turbo.hide()
        self._tarj_fan = TarjetaFan(self._set_fan)
        self._sec_fan = SeccionColapsable(
            "Modo de ventilador (ASUS)", self._tarj_fan, "fan", self._cfg
        )
        self._sec_fan.hide()
        self._bat_host = QWidget()
        self._bat_host.setAutoFillBackground(False)
        self._lay_bat = QVBoxLayout(self._bat_host)
        self._lay_bat.setContentsMargins(0, 6, 0, 0)
        self._lay_bat.setSpacing(8)
        self._sec_baterias = SeccionColapsable(
            "Baterías", self._bat_host, "baterias", self._cfg
        )
        self._sec_baterias.hide()
        self._tarj_wifi = TarjetaWifi()
        self._sec_wifi = SeccionColapsable(
            "Red Wi-Fi", self._tarj_wifi, "wifi", self._cfg
        )
        self._sec_wifi.hide()
        self._apps_host = QWidget()
        self._apps_host.setAutoFillBackground(False)
        self._lay_apps = QVBoxLayout(self._apps_host)
        self._lay_apps.setContentsMargins(0, 6, 0, 0)
        self._lay_apps.setSpacing(6)
        for _ in range(5):
            fa = TarjetaApp(on_matar=self._matar_app)
            self._filas_apps.append(fa)
            self._lay_apps.addWidget(fa)
        self._sec_apps = SeccionColapsable(
            "Apps en uso", self._apps_host, "apps", self._cfg
        )
        self._docker_host = QWidget()
        self._docker_host.setAutoFillBackground(False)
        self._lay_docker = QVBoxLayout(self._docker_host)
        self._lay_docker.setContentsMargins(0, 6, 0, 0)
        self._lay_docker.setSpacing(6)
        for _ in range(6):
            fd = TarjetaDocker(on_accion=self._accion_docker)
            self._filas_docker.append(fd)
            self._lay_docker.addWidget(fd)
            fd.hide()
        self._docker_vacio = QLabel("Sin contenedores en ejecución")
        self._docker_vacio.setObjectName("dockerVacio")
        self._docker_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lay_docker.addWidget(self._docker_vacio)
        self._sec_docker = SeccionColapsable(
            "Docker", self._docker_host, "docker", self._cfg
        )
        self._sec_docker.hide()
        temp_host = QWidget()
        temp_host.setAutoFillBackground(False)
        temp_lay = QVBoxLayout(temp_host)
        temp_lay.setContentsMargins(0, 0, 0, 0)
        temp_lay.setSpacing(8)
        self._chip_warn_temp = QLabel("")
        self._chip_warn_temp.setObjectName("chipWarnTemp")
        self._chip_warn_temp.setWordWrap(True)
        self._chip_warn_temp.setVisible(False)
        temp_lay.addWidget(self._chip_warn_temp)
        self._panel_temperaturas = PanelMultiSerie(
            "Temperatura del sistema", "°C", 35, 80, altura=130, parent=temp_host
        )
        temp_lay.addWidget(self._panel_temperaturas)
        self._sec_temperaturas = SeccionColapsable(
            "Temperaturas",
            temp_host,
            "temperaturas",
            self._cfg,
        )
        self._sec_temperaturas.hide()

        self._marco = QFrame(self)
        self._marco.setObjectName("marco")
        self._marco.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._marco.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        ext = QVBoxLayout(self)
        ext.setContentsMargins(14, 14, 14, 14)
        ext.addWidget(self._marco, 1)

        L = QVBoxLayout(self._marco)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(0)
        L.addWidget(Barra(self))

        self._scroll_main = QScrollArea()
        self._scroll_main.setWidgetResizable(True)
        self._scroll_main.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._scroll_main.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_main.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll_main.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_main.setObjectName("scrollMain")
        self._scroll_main.setAutoFillBackground(False)
        vp_dash = self._scroll_main.viewport()
        vp_dash.setObjectName("dashViewport")
        vp_dash.setAutoFillBackground(True)
        vp_dash.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        dashboard = QWidget()
        dashboard.setAutoFillBackground(False)
        dash_lay = QVBoxLayout(dashboard)
        dash_lay.setContentsMargins(18, 8, 18, 18)
        dash_lay.setSpacing(2)

        dash_lay.addWidget(self._panel_clima)
        dash_lay.addWidget(self._sec_resultados)
        dash_lay.addWidget(self._sec_descargas)
        dash_lay.addWidget(self._sec_noticias)
        dash_lay.addWidget(self._sec_tu_equipo)
        dash_lay.addWidget(self._sec_solar)
        dash_lay.addWidget(self._sec_gpu)
        dash_lay.addWidget(self._sec_turbo)
        dash_lay.addWidget(self._sec_fan)
        dash_lay.addWidget(self._sec_baterias)
        dash_lay.addWidget(self._sec_wifi)
        dash_lay.addWidget(self._sec_apps)
        dash_lay.addWidget(self._sec_docker)
        dash_lay.addWidget(self._sec_temperaturas)
        dash_lay.addStretch(1)

        self._scroll_main.setWidget(dashboard)
        L.addWidget(self._scroll_main)

    def _equipos_config(self) -> list[dict[str, str]]:
        cfg = self._cfg.setdefault("equipos", [])
        if not cfg:
            cfg.extend(
                [
                    {"liga": "bundesliga", "nombre": "Bayern Munich"},
                    {"liga": "mlb", "nombre": "Los Angeles Dodgers"},
                    {"liga": "f1"},
                ]
            )
            guardar_config(self._cfg)
        return cfg

    @staticmethod
    def _clave_equipo(eq: dict[str, str], idx: int) -> str:
        return f"{idx}|{eq.get('liga', '')}|{eq.get('nombre', '')}"

    def _abrir_dialogo_partido(self, tarj: TarjetaPartido) -> None:
        datos = tarj.datos()
        if not datos:
            return
        dlg = DialogoPartido(datos, parent=self)
        dlg.show()
        dlg._refrescar_async()

    def _aplicar_deportes(self, datos: dict[str, dict[str, Any]]) -> None:
        for clave, dat in datos.items():
            tarj = self._panel_dep.tarjetas_deportes.get(clave)
            if tarj is not None:
                tarj.actualizar(dat)
                tarj.aplicar_tema(self._tema_actual)

    def _mostrar_planeta(self, nombre: str) -> None:
        self._panel_planeta.mostrar(nombre, self._mapa_solar.posiciones)
        self._panel_planeta.aplicar_tema(self._tema_actual)

    def _tick_solar(self) -> None:
        self._mapa_solar.actualizar()
        sel = self._mapa_solar.seleccion()
        if sel:
            self._panel_planeta.mostrar(sel, self._mapa_solar.posiciones)

    def _pedir_noticias(self) -> None:
        def trabajo() -> None:
            try:
                data = obtener_top_noticias(2)
            except Exception as exc:  # noqa: BLE001
                data = {"infobae": [], "fox": [], "err": str(exc)}
            self._sig.noticias.emit(data)

        threading.Thread(target=trabajo, daemon=True).start()

    def _aplicar_noticias(self, d: dict[str, Any]) -> None:
        ac = self._tema_actual.get("acento", "#60a5fa")
        self._panel_noticias.aplicar_datos(d, ac)

    def _elegir_carpeta_descarga(self) -> None:
        pd = self._panel_desc
        d = QFileDialog.getExistingDirectory(
            self,
            "Carpeta de descargas",
            str(pd.carpeta_desc),
        )
        if d:
            pd.carpeta_desc = Path(d)
            self._cfg["descargas_carpeta"] = d
            guardar_config(self._cfg)
            pd.lbl_carpeta.setText(d)

    def _iniciar_descarga(self) -> None:
        pd = self._panel_desc
        if pd.descargando:
            return
        url = pd.ed_url.text().strip()
        if not es_url_permitida(url):
            pd.lbl_estado.setText("Pega una URL válida (https://…)")
            return
        if not yt_dlp_instalado():
            pd.lbl_estado.setText(
                "Falta yt-dlp. Ejecuta run.bat o ./run.sh de nuevo."
            )
            return
        solo_audio = pd.cb_tipo.currentIndex() == 0
        idx = pd.cb_calidad.currentIndex()
        fmt_video = CALIDADES_VIDEO[max(0, min(idx, len(CALIDADES_VIDEO) - 1))][1]

        def progreso(s: str) -> None:
            self._sig.descarga_progreso.emit(s)

        opts, nota_post = construir_opciones(
            url=url,
            solo_audio=solo_audio,
            formato_video=fmt_video,
            carpeta=pd.carpeta_desc,
            progreso=progreso,
        )

        pd.descargando = True
        pd.btn_descargar.setEnabled(False)
        pd.lbl_estado.setText("Iniciando…")

        def trabajo() -> None:
            try:
                ok, msg = ejecutar_descarga(url, opts)
                if ok and nota_post:
                    msg = f"{msg}. {nota_post}"
            except Exception as exc:  # noqa: BLE001
                ok, msg = False, limpiar_mensaje_error(str(exc))[:650]
            self._sig.descarga_fin.emit(ok, msg)

        threading.Thread(target=trabajo, daemon=True).start()

    def _on_descarga_progreso(self, texto: str) -> None:
        self._panel_desc.lbl_estado.setText(texto)

    def _on_descarga_fin(self, ok: bool, msg: str) -> None:
        pd = self._panel_desc
        pd.descargando = False
        pd.btn_descargar.setEnabled(True)
        if ok:
            pd.lbl_estado.setText(f"✓ {msg}")
        else:
            pd.lbl_estado.setText(f"Error: {msg}")

    # ---------- Tema ----------
    def _aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema_actual = tema
        grad = (
            "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 {tema['g0']}, stop:1 {tema['g1']})"
        )
        css_marco = f"""
            QWidget#marco {{
                background: {grad};
                border-radius: 28px;
                border: 1px solid {tema["borde"]};
            }}
            QFrame#barra {{
                background-color: transparent;
                border: none;
                border-top-left-radius: 28px;
                border-top-right-radius: 28px;
            }}
            QLabel#marcaBarra {{
                color: {tema["acento"]};
                font-size: 16px;
                font-weight: 300;
            }}
            QLabel#hint {{
                color: {tema["mut"]};
                font-size: 9px;
                letter-spacing: 0.05em;
            }}
            QFrame#panelClima {{
                background-color: {tema["card"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 22px;
            }}
            QFrame#orbeClima {{
                background: qradialgradient(cx:0.4, cy:0.32, radius:0.95,
                    stop:0 rgba(255,255,255,0.5),
                    stop:0.45 rgba(255,255,255,0.12),
                    stop:1 rgba(255,255,255,0.02));
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: 54px;
            }}
            QLabel#iconoHero {{
                font-size: 56px;
                background: transparent;
                border: none;
            }}
            QLabel#grande {{
                color: {tema["titulo"]};
                font-size: 84px;
                font-weight: 200;
                letter-spacing: -4px;
            }}
            QLabel#fechaHoy {{
                color: {tema["mut"]};
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.18em;
            }}
            QLabel#ciudadHeader {{
                color: {tema["sec"]};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5em;
            }}
            QLabel#estado {{
                color: {tema["sec"]};
                font-size: 14px;
                font-weight: 500;
                font-style: italic;
            }}
            QFrame#chipClima {{
                background-color: rgba(255,255,255,0.07);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 12px;
            }}
            QLabel#chipEmoji {{ font-size: 14px; }}
            QLabel#chipEtiqueta {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.18em;
            }}
            QLabel#chipValor {{
                color: {tema["titulo"]};
                font-size: 16px;
                font-weight: 600;
                letter-spacing: -0.5px;
            }}
            QLabel#humedadEtiqueta {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.2em;
            }}
            QLabel#humedadPct {{
                color: {tema["sec"]};
                font-size: 11px;
                font-weight: 600;
                min-width: 36px;
            }}
            QProgressBar#barraHumedad {{
                border: none;
                background: rgba(255,255,255,0.12);
                border-radius: 3px;
            }}
            QProgressBar#barraHumedad::chunk {{
                background-color: {tema["acento"]};
                border-radius: 3px;
            }}
            QLabel#lblFreq {{
                color: {tema["mut"]};
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.06em;
                padding-right: 4px;
            }}
            QFrame#accentSec {{
                background-color: {tema["acento"]};
                border: none;
                border-radius: 2px;
            }}
            QLabel#titSec {{
                color: {tema["sec"]};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.32em;
            }}
            QLabel#chevSec {{
                color: {tema["acento"]};
                font-size: 14px;
                font-weight: 600;
                padding-right: 4px;
            }}
            QFrame#panelSerie {{
                background-color: rgba(255,255,255,0.06);
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,0.12);
                padding: 6px 8px 8px 8px;
            }}
            QLabel#dockerVacio {{
                color: {tema["mut"]};
                font-size: 11px;
                font-style: italic;
                padding: 8px 0 8px 0;
            }}
            QFrame#panelDescargas {{
                background-color: {tema["card"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 14px;
            }}
            QLabel#descEt {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.14em;
            }}
            QLineEdit#descUrl {{
                background-color: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px;
                padding: 8px 10px;
                color: {tema["titulo"]};
                font-size: 12px;
            }}
            QComboBox#descCombo {{
                background-color: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px;
                padding: 6px 10px;
                color: {tema["titulo"]};
                font-size: 11px;
                min-height: 28px;
            }}
            QPushButton#descBtn {{
                background-color: rgba(255,255,255,0.1);
                color: {tema["titulo"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: 600;
            }}
            QPushButton#descBtnPri {{
                background-color: {tema["acento"]};
                color: #0f172a;
                border: none;
                border-radius: 8px;
                padding: 8px 18px;
                font-weight: 700;
            }}
            QLabel#descEstado {{
                color: {tema["sec"]};
                font-size: 11px;
            }}
            QLabel#descAviso {{
                color: {tema["mut"]};
                font-size: 10px;
                font-style: italic;
            }}
            QFrame#panelNoticias {{
                background-color: {tema["card"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 14px;
            }}
            QLabel#noticiaAviso {{
                color: {tema["mut"]};
                font-size: 10px;
                font-style: italic;
            }}
            QLabel#noticiaFuente {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 0.2em;
                padding-top: 6px;
            }}
            QLabel#noticiaItem {{
                color: {tema["titulo"]};
                font-size: 12px;
                font-weight: 500;
                line-height: 140%;
            }}
            QLabel#noticiaEstado {{
                color: {tema["sec"]};
                font-size: 10px;
                font-style: italic;
            }}
            QPushButton#noticiaBtn {{
                background-color: rgba(255,255,255,0.1);
                color: {tema["titulo"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 11px;
            }}
            QPushButton#noticiaBtn:hover {{
                background-color: rgba(255,255,255,0.15);
            }}
            """
        css_scroll = f"""
            QScrollArea#scrollMain {{
                background: {grad};
                border: none;
            }}
            QWidget#dashViewport {{
                background: {grad};
                border: none;
            }}
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
                margin: 4px 2px 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,0.3);
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; width: 0;
            }}
            """
        self._marco.setStyleSheet(css_marco)
        self._scroll_main.setStyleSheet(css_scroll)
        base = QColor(tema["g1"])
        pal = QPalette()
        for role in (
            QPalette.ColorRole.Window,
            QPalette.ColorRole.Base,
            QPalette.ColorRole.Button,
        ):
            pal.setColor(role, base)
        self._scroll_main.setPalette(pal)
        self._scroll_main.viewport().setPalette(pal)

        for p in (self._panel_cpu, self._panel_ram, self._panel_disk):
            p.aplicar_texto_tema(tema["mut"], tema["sec"])
        self._panel_temperaturas.aplicar_texto_tema(tema["mut"], tema["sec"])
        for tb in self._tarj_baterias.values():
            tb.aplicar_tema(tema)
        self._tarj_wifi.aplicar_tema(tema)
        for fa in self._filas_apps:
            fa.aplicar_tema(tema)
        for fd in self._filas_docker:
            fd.aplicar_tema(tema)
        self._tarj_turbo.aplicar_tema(tema)
        self._tarj_fan.aplicar_tema(tema)
        self._panel_clima.mapa_sol.aplicar_tema(tema)
        self._mapa_solar.aplicar_tema(tema)
        self._panel_planeta.aplicar_tema(tema)
        self._panel_clima.tarj_cita.aplicar_tema(tema)
        for tarj in self._panel_dep.tarjetas_deportes.values():
            tarj.aplicar_tema(tema)
        if self._panel_noticias.ultimos_datos:
            self._panel_noticias.aplicar_datos(
                self._panel_noticias.ultimos_datos,
                tema.get("acento", "#60a5fa"),
            )

    # ---------- Configuración del widget ----------
    TAMANOS = {
        "compacto": (500, 760),
        "normal": (600, 900),
        "grande": (720, 1060),
    }
    MIN_W = 440
    MIN_H = 520
    BORDE_RESIZE = 10  # px de zona sensible alrededor del borde

    def _aplicar_tamano(self, clave: str) -> None:
        if clave not in self.TAMANOS:
            clave = "normal"
        w, h = self.TAMANOS[clave]
        self.setMinimumSize(self.MIN_W, self.MIN_H)
        self.setMaximumSize(16777215, 16777215)
        self.resize(w, h)
        self._cfg["tamano"] = clave
        self._cfg["ancho"] = w
        self._cfg["alto"] = h
        guardar_config(self._cfg)
        if self._cfg.get("anclaje", "libre") != "libre":
            self._aplicar_anclaje(self._cfg["anclaje"])

    def _set_tamano(self, clave: str) -> None:
        self._aplicar_tamano(clave)

    def _ajustar_al_contenido(self) -> None:
        """Mide el sizeHint del dashboard y ajusta el ancho al contenido."""
        hint = self._scroll_main.widget().sizeHint() if self._scroll_main.widget() else self.sizeHint()
        scr = QApplication.primaryScreen()
        max_w = scr.availableGeometry().width() - 40 if scr else 1600
        max_h = scr.availableGeometry().height() - 40 if scr else 1000
        ancho = min(max_w, max(self.MIN_W, hint.width() + 36))  # margenes
        alto = min(max_h, max(self.MIN_H, self.height()))
        self.resize(ancho, alto)
        self._cfg["ancho"] = ancho
        self._cfg["alto"] = alto
        guardar_config(self._cfg)
        if self._cfg.get("anclaje", "libre") != "libre":
            self._aplicar_anclaje(self._cfg["anclaje"])

    def _aplicar_anclaje(self, clave: str) -> None:
        scr = QApplication.primaryScreen()
        if not scr:
            return
        g = scr.availableGeometry()
        margen = 20
        if clave == "ne":
            x = g.right() - self.width() - margen
            y = g.top() + margen
        elif clave == "nw":
            x = g.left() + margen
            y = g.top() + margen
        elif clave == "se":
            x = g.right() - self.width() - margen
            y = g.bottom() - self.height() - margen
        elif clave == "sw":
            x = g.left() + margen
            y = g.bottom() - self.height() - margen
        else:
            self._cfg["anclaje"] = "libre"
            guardar_config(self._cfg)
            return
        self.move(x, y)
        self._cfg["anclaje"] = clave
        guardar_config(self._cfg)

    def _set_anclaje(self, clave: str) -> None:
        self._aplicar_anclaje(clave)

    def _aplicar_capa(self, clave: str) -> None:
        self._cfg["capa"] = clave
        guardar_config(self._cfg)

        def _ajusta_flags(w: QWidget) -> None:
            flags = w.windowFlags()
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
            flags &= ~Qt.WindowType.WindowStaysOnBottomHint
            if clave == "encima":
                flags |= Qt.WindowType.WindowStaysOnTopHint
            elif clave == "debajo":
                flags |= Qt.WindowType.WindowStaysOnBottomHint
            w.setWindowFlags(flags)

        _ajusta_flags(self)
        self.show()

    def _set_capa(self, clave: str) -> None:
        self._aplicar_capa(clave)

    def _toggle_auto_ocultar(self, valor: bool) -> None:
        self._auto_ocultar = bool(valor)
        self._cfg["auto_ocultar"] = self._auto_ocultar
        guardar_config(self._cfg)
        if not self._auto_ocultar:
            self.setWindowOpacity(self._opacidad_base)

    def _toggle_autostart(self, valor: bool) -> None:
        if valor:
            lanzador = autostart.ruta_lanzador_por_defecto(Path(__file__).resolve().parent)
            ok, msg = autostart.activar(str(lanzador))
        else:
            ok, msg = autostart.desactivar()
        self._cfg["autostart"] = bool(valor) if ok else autostart.autostart_activo()
        guardar_config(self._cfg)
        if not ok:
            self._notificar_error_autostart(msg)

    def _notificar_error_autostart(self, msg: str) -> None:
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.warning(self, "Autostart", msg)

    def _toggle_modo_claro(self, valor: bool) -> None:
        self._modo_claro = bool(valor)
        self._cfg["modo_claro"] = self._modo_claro
        guardar_config(self._cfg)
        if self._modo_claro:
            self._aplicar_tema(tema_visual(3, True, claro_forzado=True))
        else:
            self._pintar_clima(self._ultimos_datos_clima or {})

    def alternar_visible(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()
            self.raise_()

    # ---------- Auto-ocultar ----------
    def enterEvent(self, e) -> None:  # type: ignore[override]
        if self._auto_ocultar:
            self.setWindowOpacity(self._opacidad_base)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # type: ignore[override]
        if self._auto_ocultar:
            self.setWindowOpacity(0.18)
        self.unsetCursor()
        super().leaveEvent(e)

    # ---------- Redimensionado manual ----------
    def _modo_resize(self, pos) -> str | None:
        b = self.BORDE_RESIZE
        x = int(pos.x())
        y = int(pos.y())
        en_d = x >= self.width() - b
        en_b = y >= self.height() - b
        en_i = x <= b
        en_t = y <= b
        if en_d and en_b:
            return "br"
        if en_i and en_b:
            return "bl"
        if en_d:
            return "r"
        if en_b:
            return "b"
        if en_i:
            return "l"
        return None

    def _cursor_para(self, modo: str | None) -> Qt.CursorShape:
        return {
            "r": Qt.CursorShape.SizeHorCursor,
            "l": Qt.CursorShape.SizeHorCursor,
            "b": Qt.CursorShape.SizeVerCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
        }.get(modo or "", Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if e.button() == Qt.MouseButton.LeftButton:
            modo = self._modo_resize(e.position())
            if modo is not None:
                self._resize_modo = modo
                self._resize_origen = (
                    e.globalPosition().toPoint().x(),
                    e.globalPosition().toPoint().y(),
                    self.width(),
                    self.height(),
                )
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if self._resize_modo and self._resize_origen and (
            e.buttons() & Qt.MouseButton.LeftButton
        ):
            ox, oy, ow, oh = self._resize_origen
            gx = e.globalPosition().toPoint().x()
            gy = e.globalPosition().toPoint().y()
            dx = gx - ox
            dy = gy - oy
            new_w, new_h = ow, oh
            new_x, new_y = self.x(), self.y()
            modo = self._resize_modo
            if "r" in modo:
                new_w = max(self.MIN_W, ow + dx)
            if "l" in modo:
                cand = max(self.MIN_W, ow - dx)
                new_x = self.x() + (self.width() - cand)
                new_w = cand
            if "b" in modo:
                new_h = max(self.MIN_H, oh + dy)
            self.setGeometry(new_x, new_y, new_w, new_h)
            e.accept()
            return
        # cursor dinámico al pasar por el borde
        modo = self._modo_resize(e.position())
        self.setCursor(self._cursor_para(modo))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if self._resize_modo:
            self._resize_modo = None
            self._resize_origen = None
            self._cfg["ancho"] = self.width()
            self._cfg["alto"] = self.height()
            guardar_config(self._cfg)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    # ---------- Eventos ----------
    def _abrir_menu(self, pos: QPoint | None = None) -> None:
        m = QMenu(self)
        m.setStyleSheet(
            """
            QMenu {
                background-color: #1f2937;
                color: #f8fafc;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item { padding: 6px 14px; border-radius: 6px; }
            QMenu::item:selected { background-color: rgba(255,255,255,0.1); }
            """
        )

        op_label = QLabel("  Opacidad")
        op_label.setStyleSheet(
            "color: rgba(255,255,255,0.7); font-size: 10px; "
            "letter-spacing: 0.18em; font-weight: 700; padding: 4px 6px;"
        )
        wa_label = QWidgetAction(m)
        wa_label.setDefaultWidget(op_label)
        m.addAction(wa_label)

        slider_w = QFrame()
        slider_lay = QHBoxLayout(slider_w)
        slider_lay.setContentsMargins(10, 0, 10, 6)
        slider_lay.setSpacing(8)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(30)
        slider.setMaximum(100)
        op_ref = self.windowOpacity()
        slider.setValue(int(op_ref * 100))
        slider.setFixedWidth(150)
        slider.setStyleSheet(
            """
            QSlider::groove:horizontal {
                height: 4px; background: rgba(255,255,255,0.18);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: """
            + self._tema_actual["acento"]
            + """;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white; border: none;
                width: 12px; height: 12px;
                margin: -4px 0; border-radius: 6px;
            }
            """
        )
        valor_lb = QLabel(f"{slider.value()} %")
        valor_lb.setStyleSheet("color: white; font-size: 11px; min-width: 36px;")

        def _on_change(v: int) -> None:
            valor_lb.setText(f"{v} %")
            self._opacidad_base = v / 100.0
            self.setWindowOpacity(self._opacidad_base)
            self._cfg["opacidad"] = self._opacidad_base
            guardar_config(self._cfg)

        slider.valueChanged.connect(_on_change)
        slider_lay.addWidget(slider, 1)
        slider_lay.addWidget(valor_lb, 0)
        wa_slider = QWidgetAction(m)
        wa_slider.setDefaultWidget(slider_w)
        m.addAction(wa_slider)

        m.addSeparator()

        m_size = m.addMenu("Tamaño")
        for clave, etiqueta in (
            ("compacto", "Compacto"),
            ("normal", "Normal"),
            ("grande", "Grande"),
        ):
            a = QAction(etiqueta, self)
            a.setCheckable(True)
            a.setChecked(self._cfg.get("tamano", "normal") == clave)
            a.triggered.connect(lambda _c=False, k=clave: self._set_tamano(k))
            m_size.addAction(a)
        m_size.addSeparator()
        a_fit = QAction("Ajustar al contenido", self)
        a_fit.triggered.connect(self._ajustar_al_contenido)
        m_size.addAction(a_fit)

        m_pos = m.addMenu("Posición")
        for clave, etiqueta in (
            ("libre", "Libre (arrastrable)"),
            ("ne", "Esquina superior derecha"),
            ("nw", "Esquina superior izquierda"),
            ("se", "Esquina inferior derecha"),
            ("sw", "Esquina inferior izquierda"),
        ):
            a = QAction(etiqueta, self)
            a.setCheckable(True)
            a.setChecked(self._cfg.get("anclaje", "libre") == clave)
            a.triggered.connect(lambda _c=False, k=clave: self._set_anclaje(k))
            m_pos.addAction(a)

        m_capa = m.addMenu("Capa")
        for clave, etiqueta in (
            ("encima", "Siempre encima"),
            ("normal", "Normal"),
            ("debajo", "Siempre debajo"),
        ):
            a = QAction(etiqueta, self)
            a.setCheckable(True)
            a.setChecked(self._cfg.get("capa", "normal") == clave)
            a.triggered.connect(lambda _c=False, k=clave: self._set_capa(k))
            m_capa.addAction(a)

        a_auto = QAction("Auto-ocultar al salir el ratón", self)
        a_auto.setCheckable(True)
        a_auto.setChecked(bool(self._cfg.get("auto_ocultar", False)))
        a_auto.triggered.connect(self._toggle_auto_ocultar)
        m.addAction(a_auto)

        a_claro = QAction("Modo claro forzado", self)
        a_claro.setCheckable(True)
        a_claro.setChecked(bool(self._cfg.get("modo_claro", False)))
        a_claro.triggered.connect(self._toggle_modo_claro)
        m.addAction(a_claro)

        a_silt = QAction("Silenciar avisos térmicos", self)
        a_silt.setCheckable(True)
        a_silt.setChecked(bool(self._cfg.get("silenciar_temp", False)))
        a_silt.triggered.connect(self._toggle_silencio_temp)
        m.addAction(a_silt)

        a_inicio = QAction("Iniciar con el sistema", self)
        a_inicio.setCheckable(True)
        a_inicio.setChecked(autostart.autostart_activo())
        a_inicio.triggered.connect(self._toggle_autostart)
        m.addAction(a_inicio)

        m.addSeparator()
        m.addAction(QAction("Editar equipos…", self, triggered=self._abrir_editor_equipos))
        m.addAction(
            QAction("Región de alertas…", self, triggered=self._abrir_region_alertas)
        )
        m.addAction(QAction("Refrescar todo", self, triggered=self._refrescar_todo))
        m.addAction(QAction("Salir", self, triggered=self.close))
        gp = self.mapToGlobal(pos) if pos is not None else QCursor.pos()
        m.exec(gp)

    def _abrir_region_alertas(self) -> None:
        from PyQt6.QtWidgets import QInputDialog

        actual = self._cfg.get("alertas_region", REGION_ALERTAS_DEFECTO)
        texto, ok = QInputDialog.getText(
            self,
            "Región de alertas",
            "Filtra por nombre de provincia / comarca\n"
            "(ej. Madrid, Sur de la Comunidad de Madrid, Sierra de Madrid…)",
            text=actual,
        )
        if not ok:
            return
        self._cfg["alertas_region"] = texto.strip()
        guardar_config(self._cfg)
        self._pedir_alertas()

    def _abrir_editor_equipos(self) -> None:
        dlg = DialogoEquipos(self._equipos_config(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._cfg["equipos"] = dlg.equipos()
            guardar_config(self._cfg)
            self._panel_dep.reconstruir()
            self._aplicar_tema(self._tema_actual)
            self._pedir_deportes()

    def _refrescar_todo(self) -> None:
        self._pedir_clima()
        self._pedir_deportes()
        self._pedir_noticias()
        self._pedir_alertas()

    # ---------- Datos ----------
    def _pedir_clima(self) -> None:
        def trabajo() -> None:
            try:
                self._sig.clima.emit(traer_clima())
            except (
                OSError,
                URLError,
                HTTPError,
                TimeoutError,
                json.JSONDecodeError,
                KeyError,
            ) as e:
                self._sig.clima.emit({"err": str(e)})

        threading.Thread(target=trabajo, daemon=True).start()

    def _pedir_deportes(self) -> None:
        equipos = list(self._equipos_config())

        def trabajo() -> None:
            resultados: dict[str, dict[str, Any]] = {}
            for idx, eq in enumerate(equipos):
                clave = self._clave_equipo(eq, idx)
                liga = eq.get("liga", "")
                try:
                    if liga == "f1":
                        resultados[clave] = traer_f1()
                    else:
                        resultados[clave] = traer_equipo(eq)
                except Exception as e:  # noqa: BLE001
                    resultados[clave] = {"err": str(e)[:80]}
            self._sig.deportes.emit(resultados)

        threading.Thread(target=trabajo, daemon=True).start()

    def _pintar_clima(self, d: dict[str, Any]) -> None:
        self._ultimos_datos_clima = d
        self._panel_clima.pintar(
            d,
            aplicar_tema_global=self._aplicar_tema,
            modo_claro=self._modo_claro,
        )

    def _tick_sistema(self) -> None:
        try:
            m = recolectar_metricas()
        except Exception:  # noqa: BLE001
            return
        self._panel_cpu.empujar(float(m["cpu_pct"]))
        self._panel_ram.empujar(float(m["ram_pct"]))
        self._panel_disk.empujar(float(m["disk_pct"]))
        ram_u = float(m["ram_used_gb"])
        ram_t = float(m["ram_total_gb"])
        self._panel_ram.set_tool_tip_valor(f"{ram_u:.1f} / {ram_t:.1f} GiB")
        df = float(m["disk_free_gb"])
        self._panel_disk.set_tool_tip_valor(f"{df:.0f} GiB libres")

        fr = cpu_freq_resumen()
        if fr.get("n"):
            actual = fr["actual"]
            mx = fr["max"]
            if actual >= 1000:
                texto = f"CPU @ {actual / 1000:.2f} GHz · {fr['n']} núcleos"
            else:
                texto = f"CPU @ {actual} MHz · {fr['n']} núcleos"
            if mx and mx > actual:
                texto += f" · máx {mx / 1000:.1f} GHz" if mx >= 1000 else f" · máx {mx} MHz"
            self._lbl_freq.setText(texto)

        try:
            gpu = recolectar_gpu()
        except Exception:  # noqa: BLE001
            gpu = None
        if gpu:
            self._tarj_gpu.actualizar(gpu)
            self._tarj_gpu.aplicar_tema(self._tema_actual)
            self._sec_gpu.show()
        else:
            self._sec_gpu.hide()

        temps: list[tuple[str, float]] = m.get("temps") or []
        temps = filtrar_temperaturas(temps)
        if temps:
            self._panel_temperaturas.actualizar(temps)
            self._panel_temperaturas.aplicar_texto_tema(
                self._tema_actual["mut"], self._tema_actual["sec"]
            )
            self._sec_temperaturas.show()
            alertas = self._gestor_temp.evaluar(temps)
            self._actualizar_chip_temp(alertas)
        else:
            self._sec_temperaturas.hide()
            self._actualizar_chip_temp([])

    def _actualizar_chip_temp(self, alertas: list[dict[str, Any]]) -> None:
        if not alertas:
            self._chip_warn_temp.setVisible(False)
            self._chip_warn_temp.setText("")
            return
        top = alertas[0]
        nivel = top["nivel"]
        if nivel == "crit":
            color = "#ef4444"
            emoji = "🔥"
            etiqueta = "CRÍTICA"
        else:
            color = "#f97316"
            emoji = "🌡️"
            etiqueta = "ALTA"
        nombre = (top["nombre"] or "?")[:24]
        valor = top["valor"]
        umbral = top["crit"] if nivel == "crit" else top["warn"]
        n_extra = len(alertas) - 1
        suf = f"  ·  +{n_extra} sensor{'es' if n_extra != 1 else ''}" if n_extra > 0 else ""
        self._chip_warn_temp.setText(
            f"{emoji}  TEMPERATURA {etiqueta}   ·   {nombre}: "
            f"{valor:.0f}°C  (umbral {umbral:.0f}°C){suf}"
        )
        self._chip_warn_temp.setStyleSheet(
            f"""
            QLabel#chipWarnTemp {{
                background-color: rgba(0,0,0,0.30);
                color: white;
                border: 1px solid {color};
                border-left: 4px solid {color};
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.04em;
            }}
            """
        )
        tip_lineas = [
            f"{a['nombre']}: {a['valor']:.1f} °C "
            f"(warn {a['warn']:.0f} · crit {a['crit']:.0f}) [{a['nivel']}]"
            for a in alertas
        ]
        self._chip_warn_temp.setToolTip("\n".join(tip_lineas))
        self._chip_warn_temp.setVisible(True)

    def _notificar_temp_handler(
        self, nombre: str, valor: float, nivel: str, umbral: float
    ) -> None:
        urgencia = "critical" if nivel == "crit" else "normal"
        emoji = "🔥" if nivel == "crit" else "🌡️"
        titulo = f"{emoji} Temperatura {'crítica' if nivel == 'crit' else 'alta'}"
        cuerpo = (
            f"<b>{nombre}</b> está a <b>{valor:.0f} °C</b>\n"
            f"(umbral {umbral:.0f} °C)"
        )
        icono = "dialog-error" if nivel == "crit" else "dialog-warning"

        def trabajo() -> None:
            try:
                notificar_escritorio(
                    titulo, cuerpo, urgencia=urgencia, icono=icono
                )
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=trabajo, daemon=True).start()

    def _toggle_silencio_temp(self, valor: bool) -> None:
        self._gestor_temp.silenciado = bool(valor)
        self._cfg["silenciar_temp"] = bool(valor)
        guardar_config(self._cfg)

    def _tick_baterias(self) -> None:
        try:
            datos = recolectar_baterias()
        except Exception:  # noqa: BLE001
            datos = []
        ids_actuales = {d["id"] for d in datos}
        for old_id in list(self._tarj_baterias):
            if old_id not in ids_actuales:
                w = self._tarj_baterias.pop(old_id)
                self._lay_bat.removeWidget(w)
                w.deleteLater()
        for d in datos:
            tarj = self._tarj_baterias.get(d["id"])
            if tarj is None:
                tarj = TarjetaBateria(d, parent=self._bat_host)
                tarj.aplicar_tema(self._tema_actual)
                self._lay_bat.addWidget(tarj)
                self._tarj_baterias[d["id"]] = tarj
            else:
                tarj.actualizar(d)
                tarj.aplicar_tema(self._tema_actual)
        if self._tarj_baterias:
            self._sec_baterias.show()
        else:
            self._sec_baterias.hide()

    def _tick_red(self) -> None:
        try:
            datos = self._monitor_red.tick()
        except Exception:  # noqa: BLE001
            datos = None
        if datos is None:
            self._sec_wifi.hide()
            return
        self._tarj_wifi.actualizar(datos)
        self._tarj_wifi.aplicar_tema(self._tema_actual)
        self._sec_wifi.show()

    def _tick_apps(self) -> None:
        try:
            top = self._monitor_apps.top_n(len(self._filas_apps))
        except Exception:  # noqa: BLE001
            top = []
        for i, fa in enumerate(self._filas_apps):
            if i < len(top):
                fa.actualizar(top[i])
                fa.aplicar_tema(self._tema_actual)
                fa.show()
            else:
                fa.hide()

    def _tick_docker(self) -> None:
        rows = listar_docker()
        if rows is None:
            self._sec_docker.hide()
            return
        self._sec_docker.show()
        rows = rows[: len(self._filas_docker)]
        stats = self._docker_stats_cache
        for i, fd in enumerate(self._filas_docker):
            if i < len(rows):
                info = rows[i]
                fd.actualizar(info, stats.get(info.get("nombre") or ""))
                fd.aplicar_tema(self._tema_actual)
                fd.show()
            else:
                fd.hide()
        self._docker_vacio.setVisible(len(rows) == 0)

    def _refrescar_docker_stats(self) -> None:
        """Calcula `docker stats` en un hilo (es lento) y guarda en caché."""

        def trabajo() -> None:
            try:
                self._docker_stats_cache = stats_docker()
            except Exception:  # noqa: BLE001
                self._docker_stats_cache = {}

        threading.Thread(target=trabajo, daemon=True).start()

    def _accion_docker(self, nombre: str, accion: str) -> None:
        def trabajo() -> None:
            accion_docker(nombre, accion)
            QTimer.singleShot(200, self._tick_docker)
            QTimer.singleShot(200, self._refrescar_docker_stats)

        threading.Thread(target=trabajo, daemon=True).start()

    def _matar_app(self, pids: list[int]) -> None:
        def trabajo() -> None:
            matar_proceso(pids)
            QTimer.singleShot(100, self._tick_apps)

        threading.Thread(target=trabajo, daemon=True).start()

    def _refrescar_ping(self) -> None:
        def trabajo() -> None:
            try:
                self._monitor_red.actualizar_ping()
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=trabajo, daemon=True).start()

    def _refrescar_ip_publica(self) -> None:
        def trabajo() -> None:
            try:
                ip_publica()
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=trabajo, daemon=True).start()

    def _tick_turbo(self) -> None:
        info = estado_turbo()
        if info is None:
            self._sec_turbo.hide()
            return
        self._sec_turbo.show()
        self._tarj_turbo.set_estado(info)
        self._tarj_turbo.aplicar_tema(self._tema_actual)

    def _toggle_turbo(self, activar: bool) -> None:
        def trabajo() -> None:
            ok, _msg = cambiar_turbo(activar)
            QTimer.singleShot(50, self._tick_turbo)
            if not ok:
                QTimer.singleShot(50, self._tick_turbo)

        threading.Thread(target=trabajo, daemon=True).start()

    def _tick_fan(self) -> None:
        info = estado_fan()
        if info is None:
            self._sec_fan.hide()
            return
        self._sec_fan.show()
        self._tarj_fan.set_estado(info)
        self._tarj_fan.aplicar_tema(self._tema_actual)

    def _set_fan(self, valor: int) -> None:
        def trabajo() -> None:
            ok, mensaje = cambiar_fan(valor)
            QTimer.singleShot(
                80,
                lambda: (
                    self._tarj_fan.set_resultado(ok, mensaje),
                    self._tick_fan(),
                ),
            )

        threading.Thread(target=trabajo, daemon=True).start()

    def _tick_cita(self) -> None:
        self._panel_clima.tarj_cita.refrescar()

    def _pedir_alertas(self) -> None:
        pais = self._cfg.get("alertas_pais", "spain")
        region = self._cfg.get("alertas_region")
        if region is None:
            region = REGION_ALERTAS_DEFECTO

        def trabajo() -> None:
            try:
                avisos = traer_alertas_meteo(pais, region or None)
            except Exception:  # noqa: BLE001
                avisos = []
            self._sig.alertas.emit(avisos)

        threading.Thread(target=trabajo, daemon=True).start()

    def _aplicar_alertas(self, avisos: list[dict[str, Any]]) -> None:
        info = resumen_alertas(avisos or [])
        chip = self._panel_clima.chip_alerta
        if not info:
            chip.setVisible(False)
            return
        n_extra = info["n"] - 1
        suf = f" · +{n_extra}" if n_extra > 0 else ""
        area = info.get("area", "")
        texto = f"{info['emoji']}  {info['titulo'].upper()}{suf}"
        if area:
            texto += f"   {area}"
        chip.setText(texto)
        sev = info["severidad"]
        col = info["color"]
        chip.setStyleSheet(
            f"""
            QLabel#chipAlerta {{
                background-color: rgba(0,0,0,0.30);
                color: white;
                border: 1px solid {col};
                border-left: 4px solid {col};
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.04em;
            }}
            """
        )
        chip.setToolTip(
            f"{len(avisos)} aviso(s) de nivel {sev} en {info.get('area') or 'tu zona'}"
        )
        chip.setVisible(True)

    def closeEvent(self, e: QCloseEvent) -> None:
        for t in (
            self._t_clima,
            self._t_sys,
            self._t_deportes,
            self._t_bat,
            self._t_red,
            self._t_apps,
            self._t_docker,
            self._t_docker_stats,
            self._t_ping,
            self._t_ippub,
            self._t_turbo,
            self._t_fan,
            self._t_cita,
            self._t_alertas,
        ):
            t.stop()
        super().closeEvent(e)


def _instalar_atajo_global(w: "Ventana") -> None:
    """Toggle al recibir SIGUSR1 (solo Unix). En Windows no aplica."""
    try:
        import signal

        if not hasattr(signal, "SIGUSR1"):
            return

        def _handler(_sig, _frm) -> None:
            QTimer.singleShot(0, w.alternar_visible)

        signal.signal(signal.SIGUSR1, _handler)
    except (AttributeError, ValueError, OSError):
        pass


def main() -> int:
    try:
        import psutil

        psutil.cpu_percent(interval=0.05)
    except Exception:  # noqa: BLE001
        pass
    pg.setConfigOptions(antialias=True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    f = QFont("Ubuntu", 11)
    if hasattr(f, "setFamilies"):
        f.setFamilies(
            ["Inter", "IBM Plex Sans", "Ubuntu", "Segoe UI", "sans-serif"]
        )
    app.setFont(f)
    w = Ventana()
    _instalar_atajo_global(w)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
