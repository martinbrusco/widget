"""Vista cenital del sistema solar con posiciones reales y datos por planeta.

Cálculo orbital basado en elementos keplerianos J2000 (NASA/JPL,
'Approximate Positions of the Planets', Standish 1992) con derivadas
lineales por siglo. Precisión típica: < 1° para 1800-2050.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

# --- Elementos orbitales J2000 -------------------------------------------------
# Cada entrada: (valor en J2000, tasa por siglo julián)
# a (UA), e, i (°), L (long. media, °), long_peri (°), long_node (°)

@dataclass(frozen=True)
class ElementosOrbitales:
    a: tuple[float, float]
    e: tuple[float, float]
    i: tuple[float, float]
    L: tuple[float, float]
    long_peri: tuple[float, float]
    long_node: tuple[float, float]


PLANETAS: dict[str, dict[str, Any]] = {
    "Mercurio": {
        "elem": ElementosOrbitales(
            a=(0.38709927, 0.00000037),
            e=(0.20563593, 0.00001906),
            i=(7.00497902, -0.00594749),
            L=(252.25032350, 149472.67411175),
            long_peri=(77.45779628, 0.16047689),
            long_node=(48.33076593, -0.12534081),
        ),
        "color": "#bfbfbf",
        "radio_km": 2_439.7,
        "masa_kg": 3.3011e23,
        "gravedad": 3.70,
        "dia_h": 1407.5,
        "anyo_d": 88.0,
        "lunas": 0,
        "atmosfera": "Prácticamente inexistente (exosfera de Na, K).",
        "temperatura": "−180 a +430 °C",
        "curiosidad": (
            "Su día solar dura 176 días terrestres, dos años mercurianos. "
            "El núcleo ocupa el 85 % del radio."
        ),
        "tam_pix": 6,
    },
    "Venus": {
        "elem": ElementosOrbitales(
            a=(0.72333566, 0.00000390),
            e=(0.00677672, -0.00004107),
            i=(3.39467605, -0.00078890),
            L=(181.97909950, 58517.81538729),
            long_peri=(131.60246718, 0.00268329),
            long_node=(76.67984255, -0.27769418),
        ),
        "color": "#e3c97f",
        "radio_km": 6_051.8,
        "masa_kg": 4.8675e24,
        "gravedad": 8.87,
        "dia_h": 5832.5,
        "anyo_d": 224.7,
        "lunas": 0,
        "atmosfera": "CO₂ 96.5 %, N₂ 3.5 %. Presión 92 atm.",
        "temperatura": "+462 °C (superficie)",
        "curiosidad": (
            "Rota retrógrado: el Sol sale por el oeste. "
            "Es el planeta más caliente del sistema, por su efecto invernadero."
        ),
        "tam_pix": 8,
    },
    "Tierra": {
        "elem": ElementosOrbitales(
            a=(1.00000261, 0.00000562),
            e=(0.01671123, -0.00004392),
            i=(-0.00001531, -0.01294668),
            L=(100.46457166, 35999.37244981),
            long_peri=(102.93768193, 0.32327364),
            long_node=(0.0, 0.0),
        ),
        "color": "#3b82f6",
        "radio_km": 6_371.0,
        "masa_kg": 5.972e24,
        "gravedad": 9.807,
        "dia_h": 23.934,
        "anyo_d": 365.256,
        "lunas": 1,
        "atmosfera": "N₂ 78 %, O₂ 21 %, Ar 0.93 %, CO₂ 0.04 %.",
        "temperatura": "−89 a +57 °C  (media +15 °C)",
        "curiosidad": (
            "El único mundo conocido con vida. Su Luna estabiliza el eje, "
            "manteniendo las estaciones."
        ),
        "tam_pix": 9,
    },
    "Marte": {
        "elem": ElementosOrbitales(
            a=(1.52371034, 0.00001847),
            e=(0.09339410, 0.00007882),
            i=(1.84969142, -0.00813131),
            L=(-4.55343205, 19140.30268499),
            long_peri=(-23.94362959, 0.44441088),
            long_node=(49.55953891, -0.29257343),
        ),
        "color": "#e1604a",
        "radio_km": 3_389.5,
        "masa_kg": 6.4171e23,
        "gravedad": 3.71,
        "dia_h": 24.6229,
        "anyo_d": 686.97,
        "lunas": 2,
        "atmosfera": "CO₂ 95 %, N₂ 2.8 %, Ar 2 %. Presión 0.6 % terrestre.",
        "temperatura": "−143 a +35 °C",
        "curiosidad": (
            "Hogar de Olympus Mons (22 km), la mayor montaña del sistema solar. "
            "Sus dos lunas, Fobos y Deimos, son asteroides capturados."
        ),
        "tam_pix": 7,
    },
    "Júpiter": {
        "elem": ElementosOrbitales(
            a=(5.20288700, -0.00011607),
            e=(0.04838624, -0.00013253),
            i=(1.30439695, -0.00183714),
            L=(34.39644051, 3034.74612775),
            long_peri=(14.72847983, 0.21252668),
            long_node=(100.47390909, 0.20469106),
        ),
        "color": "#d6a06b",
        "radio_km": 69_911.0,
        "masa_kg": 1.8982e27,
        "gravedad": 24.79,
        "dia_h": 9.9259,
        "anyo_d": 4_332.59,
        "lunas": 95,
        "atmosfera": "H₂ 90 %, He 10 %.",
        "temperatura": "−108 °C (cima de nubes)",
        "curiosidad": (
            "La Gran Mancha Roja es una tormenta más grande que la Tierra "
            "que lleva al menos 350 años activa."
        ),
        "tam_pix": 14,
    },
    "Saturno": {
        "elem": ElementosOrbitales(
            a=(9.53667594, -0.00125060),
            e=(0.05386179, -0.00050991),
            i=(2.48599187, 0.00193609),
            L=(49.95424423, 1222.49362201),
            long_peri=(92.59887831, -0.41897216),
            long_node=(113.66242448, -0.28867794),
        ),
        "color": "#e6d6a3",
        "radio_km": 58_232.0,
        "masa_kg": 5.6834e26,
        "gravedad": 10.44,
        "dia_h": 10.656,
        "anyo_d": 10_759.22,
        "lunas": 146,
        "atmosfera": "H₂ 96 %, He 3 %.",
        "temperatura": "−138 °C (cima de nubes)",
        "curiosidad": (
            "Su densidad es menor que la del agua: si hubiese un océano "
            "lo bastante grande, Saturno flotaría."
        ),
        "tam_pix": 12,
    },
    "Urano": {
        "elem": ElementosOrbitales(
            a=(19.18916464, -0.00196176),
            e=(0.04725744, -0.00004397),
            i=(0.77263783, -0.00242939),
            L=(313.23810451, 428.48202785),
            long_peri=(170.95427630, 0.40805281),
            long_node=(74.01692503, 0.04240589),
        ),
        "color": "#9fd8e4",
        "radio_km": 25_362.0,
        "masa_kg": 8.681e25,
        "gravedad": 8.69,
        "dia_h": 17.24,
        "anyo_d": 30_688.5,
        "lunas": 27,
        "atmosfera": "H₂ 83 %, He 15 %, CH₄ 2 %.",
        "temperatura": "−197 °C",
        "curiosidad": (
            "Rueda casi de costado: su eje está inclinado 98°. "
            "Tarda 84 años en orbitar al Sol."
        ),
        "tam_pix": 10,
    },
    "Neptuno": {
        "elem": ElementosOrbitales(
            a=(30.06992276, 0.00026291),
            e=(0.00859048, 0.00005105),
            i=(1.77004347, 0.00035372),
            L=(-55.12002969, 218.45945325),
            long_peri=(44.96476227, -0.32241464),
            long_node=(131.78422574, -0.00508664),
        ),
        "color": "#4f7be7",
        "radio_km": 24_622.0,
        "masa_kg": 1.02413e26,
        "gravedad": 11.15,
        "dia_h": 16.11,
        "anyo_d": 60_182.0,
        "lunas": 14,
        "atmosfera": "H₂ 80 %, He 19 %, CH₄ 1 %.",
        "temperatura": "−201 °C",
        "curiosidad": (
            "Vientos supersónicos de hasta 2 100 km/h, los más rápidos del "
            "sistema solar. Descubierto matemáticamente antes que ópticamente."
        ),
        "tam_pix": 10,
    },
}

ORDEN_PLANETAS = list(PLANETAS.keys())


def _jd(ahora: datetime | None = None) -> float:
    if ahora is None:
        ahora = datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    ahora = ahora.astimezone(timezone.utc)
    timestamp = ahora.timestamp()
    return 2440587.5 + timestamp / 86400.0


def _resolver_kepler(M: float, e: float) -> float:
    """Resuelve M = E - e·sin(E) por Newton-Raphson. M, E en radianes."""
    M = (M + math.pi) % (2 * math.pi) - math.pi
    E = M + e * math.sin(M)
    for _ in range(8):
        delta = (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        E -= delta
        if abs(delta) < 1e-9:
            break
    return E


def _coords(elem: ElementosOrbitales, T: float) -> tuple[float, float, float]:
    """Devuelve (x, y, z) heliocéntricas eclípticas en UA."""
    a = elem.a[0] + elem.a[1] * T
    e = elem.e[0] + elem.e[1] * T
    i = math.radians(elem.i[0] + elem.i[1] * T)
    L = elem.L[0] + elem.L[1] * T
    lp = elem.long_peri[0] + elem.long_peri[1] * T
    ln = elem.long_node[0] + elem.long_node[1] * T

    M = math.radians((L - lp) % 360.0)
    omega = math.radians((lp - ln) % 360.0)
    Omega = math.radians(ln % 360.0)

    E = _resolver_kepler(M, e)
    xp = a * (math.cos(E) - e)
    yp = a * math.sqrt(max(0.0, 1.0 - e * e)) * math.sin(E)

    co, so = math.cos(omega), math.sin(omega)
    cO, sO = math.cos(Omega), math.sin(Omega)
    ci, si = math.cos(i), math.sin(i)

    x = (co * cO - so * sO * ci) * xp + (-so * cO - co * sO * ci) * yp
    y = (co * sO + so * cO * ci) * xp + (-so * sO + co * cO * ci) * yp
    z = (so * si) * xp + (co * si) * yp
    return x, y, z


def posiciones_planetas(
    ahora: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Devuelve para cada planeta posición (x,y,z) UA, distancia al Sol y a la Tierra."""
    T = (_jd(ahora) - 2451545.0) / 36525.0
    out: dict[str, dict[str, Any]] = {}
    for nombre, info in PLANETAS.items():
        x, y, z = _coords(info["elem"], T)
        r = math.sqrt(x * x + y * y + z * z)
        out[nombre] = {"pos": (x, y, z), "r_au": r}
    tierra = out["Tierra"]["pos"]
    for nombre, d in out.items():
        x, y, z = d["pos"]
        dx, dy, dz = x - tierra[0], y - tierra[1], z - tierra[2]
        d["d_tierra_au"] = math.sqrt(dx * dx + dy * dy + dz * dz)
    return out


# --- UI ----------------------------------------------------------------------

UA_KM = 149_597_870.7


def _fmt_grande(n: float, suf: str) -> str:
    if n >= 1e12:
        return f"{n / 1e12:.2f} × 10¹² {suf}"
    if n >= 1e9:
        return f"{n / 1e9:.2f} mil mill. {suf}"
    if n >= 1e6:
        return f"{n / 1e6:.2f} millones {suf}"
    if n >= 1e3:
        return f"{n / 1e3:.0f} mil {suf}"
    return f"{n:.1f} {suf}"


def _fmt_anyo(d: float) -> str:
    if d < 365:
        return f"{d:.1f} días"
    return f"{d / 365.25:.2f} años terrestres"


def _fmt_dia(h: float) -> str:
    if h < 24:
        return f"{h:.2f} h"
    return f"{h / 24.0:.2f} días terrestres"


def _fmt_masa(kg: float) -> str:
    return f"{kg:.3e} kg"


class MapaSistemaSolar(QWidget):
    """Vista cenital interactiva del sistema solar."""

    planeta_clic = pyqtSignal(str)

    MARGEN = 14

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setMaximumHeight(280)
        self.setMouseTracking(True)
        self._tema: dict[str, str] = {}
        self._posiciones: dict[str, dict[str, Any]] = posiciones_planetas()
        self._centro = QPointF(0, 0)
        self._escala = 1.0
        self._radios: dict[str, float] = {}
        self._puntos_pix: dict[str, QPointF] = {}
        self._hover: str | None = None
        self._sel: str | None = None
        self._max_au = max(p["r_au"] for p in self._posiciones.values())

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self.update()

    def actualizar(self) -> None:
        self._posiciones = posiciones_planetas()
        self.update()

    @property
    def posiciones(self) -> dict[str, dict[str, Any]]:
        return self._posiciones

    def seleccion(self) -> str | None:
        return self._sel

    def set_seleccion(self, nombre: str | None) -> None:
        self._sel = nombre
        self.update()

    def _radio_pix(self, r_au: float) -> float:
        # escala logarítmica: comprime el rango Mercurio–Neptuno (0.39–30 UA)
        r0 = 0.3
        rmax = self._max_au * 1.05
        if r_au <= r0:
            return self._radio_min
        return self._radio_min + (self._radio_max - self._radio_min) * (
            math.log10(r_au / r0) / math.log10(rmax / r0)
        )

    def _recalcular(self) -> None:
        w = self.width()
        h = self.height()
        self._centro = QPointF(w / 2, h / 2)
        radio_disp = min(w, h) / 2 - self.MARGEN
        self._radio_min = max(18, radio_disp * 0.10)
        self._radio_max = max(self._radio_min + 10, radio_disp * 0.95)
        self._radios = {
            nombre: self._radio_pix(d["r_au"]) for nombre, d in self._posiciones.items()
        }
        for nombre, d in self._posiciones.items():
            x, y, _ = d["pos"]
            ang = math.atan2(y, x)
            r_pix = self._radios[nombre]
            px = self._centro.x() + r_pix * math.cos(ang)
            py = self._centro.y() - r_pix * math.sin(ang)
            self._puntos_pix[nombre] = QPointF(px, py)

    def paintEvent(self, _e) -> None:  # type: ignore[override]
        self._recalcular()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())
        path_round = QPainterPath()
        path_round.addRoundedRect(rect, 16, 16)
        p.setClipPath(path_round)

        bg = QRadialGradient(self._centro, max(self.width(), self.height()) / 1.2)
        bg.setColorAt(0.0, QColor(12, 18, 38))
        bg.setColorAt(0.7, QColor(4, 8, 22))
        bg.setColorAt(1.0, QColor(2, 4, 14))
        p.fillRect(rect, bg)

        # Estrellas de fondo (deterministas)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        for k in range(60):
            sx = (k * 73 + 17) % int(self.width())
            sy = (k * 41 + 31) % int(self.height())
            r = 1 if k % 7 else 1.4
            p.setBrush(QColor(255, 255, 255, 70 + (k * 13) % 80))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(sx, sy), r, r)

        # Órbitas
        for nombre, r_pix in self._radios.items():
            color = QColor(PLANETAS[nombre]["color"])
            color.setAlpha(60 if nombre != self._sel else 160)
            pen = QPen(color, 1.2 if nombre == self._sel else 1.0)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self._centro, r_pix, r_pix)

        # Sol con halo
        sol_r = 8
        halo = QRadialGradient(self._centro, sol_r * 5)
        halo.setColorAt(0.0, QColor(255, 220, 130, 180))
        halo.setColorAt(0.4, QColor(255, 200, 100, 60))
        halo.setColorAt(1.0, QColor(255, 200, 100, 0))
        p.setBrush(QBrush(halo))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(self._centro, sol_r * 5, sol_r * 5)
        p.setBrush(QColor(255, 235, 180))
        p.setPen(QPen(QColor(255, 255, 220, 220), 1))
        p.drawEllipse(self._centro, sol_r, sol_r)

        # Planetas
        for nombre, pt in self._puntos_pix.items():
            info = PLANETAS[nombre]
            color = QColor(info["color"])
            tam = info["tam_pix"] / 2.0
            if nombre == self._hover or nombre == self._sel:
                glow = QRadialGradient(pt, tam * 4)
                glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 200))
                glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
                p.setBrush(QBrush(glow))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(pt, tam * 4, tam * 4)
            p.setBrush(color)
            p.setPen(QPen(QColor(255, 255, 255, 160 if nombre == self._sel else 90), 1))
            p.drawEllipse(pt, tam, tam)

            if nombre == self._sel:
                p.setPen(QPen(QColor(255, 255, 255, 220), 1))
                p.drawText(
                    QRectF(pt.x() + tam + 4, pt.y() - 9, 90, 18),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    nombre,
                )

        # Marco
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
        p.end()

    def _planeta_en(self, pos: QPointF) -> str | None:
        mejor: str | None = None
        mejor_d = 1e9
        for nombre, pt in self._puntos_pix.items():
            tam = max(8.0, PLANETAS[nombre]["tam_pix"] / 2.0 + 4)
            dx = pos.x() - pt.x()
            dy = pos.y() - pt.y()
            d = math.hypot(dx, dy)
            if d < tam and d < mejor_d:
                mejor = nombre
                mejor_d = d
        return mejor

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        n = self._planeta_en(e.position())
        if n != self._hover:
            self._hover = n
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if n is not None
                else Qt.CursorShape.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if e.button() == Qt.MouseButton.LeftButton:
            n = self._planeta_en(e.position())
            if n is not None:
                self._sel = n
                self.update()
                self.planeta_clic.emit(n)
        super().mousePressEvent(e)


class PanelInfoPlaneta(QFrame):
    """Tarjeta lateral con datos del planeta seleccionado."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardPlaneta")
        self.setAutoFillBackground(False)
        L = QVBoxLayout(self)
        L.setContentsMargins(14, 12, 14, 12)
        L.setSpacing(8)

        cab = QHBoxLayout()
        cab.setSpacing(10)
        self._punto = QLabel(" ")
        self._punto.setObjectName("planetaDot")
        self._punto.setFixedSize(14, 14)
        col = QVBoxLayout()
        col.setSpacing(2)
        self._nombre = QLabel("Selecciona un planeta")
        self._nombre.setObjectName("planetaNombre")
        self._sub = QLabel("Haz clic sobre cualquier órbita")
        self._sub.setObjectName("planetaSub")
        self._sub.setWordWrap(True)
        col.addWidget(self._nombre)
        col.addWidget(self._sub)
        cab.addWidget(self._punto, 0, Qt.AlignmentFlag.AlignTop)
        cab.addLayout(col, 1)
        L.addLayout(cab)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(8)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        L.addLayout(self._grid)

        self._extra = QVBoxLayout()
        self._extra.setSpacing(8)
        L.addLayout(self._extra)

        self._curiosidad = QLabel("")
        self._curiosidad.setObjectName("planetaCuriosidad")
        self._curiosidad.setWordWrap(True)
        L.addWidget(self._curiosidad)
        self._tema: dict[str, str] = {}

    def _limpiar_layout(self, lay) -> None:
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            elif it.layout() is not None:
                self._limpiar_layout(it.layout())

    def _bloque_stat(self, etiqueta: str, valor: str) -> QWidget:
        cont = QFrame()
        cont.setObjectName("planetaStat")
        cont.setAutoFillBackground(False)
        v = QVBoxLayout(cont)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(2)
        et = QLabel(etiqueta.upper())
        et.setObjectName("planetaEt")
        et.setWordWrap(True)
        val = QLabel(valor)
        val.setObjectName("planetaVal")
        val.setWordWrap(True)
        v.addWidget(et)
        v.addWidget(val)
        return cont

    def _bloque_ancho(self, etiqueta: str, valor: str) -> QWidget:
        return self._bloque_stat(etiqueta, valor)

    def mostrar(
        self, nombre: str, posiciones: dict[str, dict[str, Any]]
    ) -> None:
        info = PLANETAS.get(nombre)
        if info is None:
            return
        pos = posiciones.get(nombre, {})
        r_au = float(pos.get("r_au", 0.0))
        d_t = float(pos.get("d_tierra_au", 0.0))
        self._punto.setStyleSheet(
            f"background:{info['color']}; border-radius:7px; border: 1px solid rgba(255,255,255,0.3);"
        )
        self._nombre.setText(nombre)
        self._sub.setText(
            f"Distancia al Sol: {r_au:.3f} UA "
            f"({_fmt_grande(r_au * UA_KM, 'km')})"
        )

        self._limpiar_layout(self._grid)
        self._limpiar_layout(self._extra)

        pares = [
            ("Distancia a Tierra", f"{d_t:.3f} UA"),
            ("Radio ecuatorial", _fmt_grande(info["radio_km"] * 1000, "m")),
            ("Masa", _fmt_masa(info["masa_kg"])),
            ("Gravedad", f"{info['gravedad']:.2f} m/s²"),
            ("Día (rotación)", _fmt_dia(info["dia_h"])),
            ("Año (órbita)", _fmt_anyo(info["anyo_d"])),
            ("Lunas conocidas", str(info["lunas"])),
            ("Temperatura", info["temperatura"]),
        ]
        for i, (et, val) in enumerate(pares):
            self._grid.addWidget(self._bloque_stat(et, val), i // 2, i % 2)

        self._extra.addWidget(self._bloque_ancho("Atmósfera", info["atmosfera"]))

        self._curiosidad.setText("✦  " + info["curiosidad"])
        if self._tema:
            self.aplicar_tema(self._tema)

    def aplicar_tema(self, tema: dict[str, str]) -> None:
        self._tema = tema
        self.setStyleSheet(
            f"""
            QFrame#cardPlaneta {{
                background-color: {tema["card"]};
                border: 1px solid {tema["card_borde"]};
                border-radius: 14px;
            }}
            QFrame#planetaStat {{
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
            }}
            QLabel#planetaNombre {{
                color: {tema["titulo"]};
                font-size: 15px;
                font-weight: 700;
                letter-spacing: 0.04em;
            }}
            QLabel#planetaSub {{
                color: {tema["sec"]};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#planetaEt {{
                color: {tema["mut"]};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.12em;
            }}
            QLabel#planetaVal {{
                color: {tema["titulo"]};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#planetaCuriosidad {{
                color: {tema["sec"]};
                font-size: 11px;
                font-style: italic;
                line-height: 140%;
                padding-top: 6px;
                border-top: 1px solid rgba(255,255,255,0.08);
            }}
            """
        )
