"""Paneles del dashboard: cada bloque es un QWidget independiente con objectName estable.

Permite aplicar QSS por sección (p. ej. QWidget#panelClima {{ … }}).
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from deportes import LIGAS_TSD, TarjetaPartido
from descargas_media import CALIDADES_VIDEO, yt_dlp_instalado


def _clave_equipo(eq: dict[str, str], idx: int) -> str:
    return f"{idx}|{eq.get('liga', '')}|{eq.get('nombre', '')}"


class PanelClima(QFrame):
    """Clima principal: ubicación, temperatura, chips y mapa solar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panelClima")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        import widget as W

        L = QVBoxLayout(self)
        L.setContentsMargins(20, 18, 20, 18)
        L.setSpacing(12)

        fila_fecha = QHBoxLayout()
        self.fecha = QLabel(W.texto_fecha_es())
        self.fecha.setObjectName("fechaHoy")
        self.ciudad = QLabel(W.CIUDAD.upper())
        self.ciudad.setObjectName("ciudadHeader")
        fila_fecha.addWidget(self.fecha, 0, Qt.AlignmentFlag.AlignLeft)
        fila_fecha.addStretch(1)
        fila_fecha.addWidget(self.ciudad, 0, Qt.AlignmentFlag.AlignRight)
        L.addLayout(fila_fecha)

        hero = QHBoxLayout()
        hero.setSpacing(10)
        col_izq = QVBoxLayout()
        col_izq.setSpacing(2)
        self.temp = QLabel("—")
        self.temp.setObjectName("grande")
        self.temp.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.estado_txt = QLabel("…")
        self.estado_txt.setObjectName("estado")
        self.estado_txt.setWordWrap(True)
        col_izq.addWidget(self.temp)
        col_izq.addWidget(self.estado_txt)
        hero.addLayout(col_izq, 1)

        self.orbe = QFrame()
        self.orbe.setObjectName("orbeClima")
        self.orbe.setFixedSize(108, 108)
        orbe_lay = QVBoxLayout(self.orbe)
        orbe_lay.setContentsMargins(0, 0, 0, 0)
        self.icono = QLabel("🌤️")
        self.icono.setObjectName("iconoHero")
        self.icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orbe_lay.addWidget(self.icono)
        hero.addWidget(
            self.orbe,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        L.addLayout(hero)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chip_sens = self._chip("Sensación", "—°", "🌡️")
        self.chip_hum = self._chip("Humedad", "—%", "💧")
        self.chip_viento = self._chip("Viento", "—", "🍃")
        chips.addWidget(self.chip_sens["wrap"])
        chips.addWidget(self.chip_hum["wrap"])
        chips.addWidget(self.chip_viento["wrap"])
        L.addLayout(chips)

        fila_h = QHBoxLayout()
        fila_h.setSpacing(10)
        et_h = QLabel("HUMEDAD RELATIVA")
        et_h.setObjectName("humedadEtiqueta")
        self.bar_humedad = QProgressBar()
        self.bar_humedad.setObjectName("barraHumedad")
        self.bar_humedad.setRange(0, 100)
        self.bar_humedad.setTextVisible(False)
        self.bar_humedad.setFixedHeight(6)
        self.humedad_pct = QLabel("—")
        self.humedad_pct.setObjectName("humedadPct")
        fila_h.addWidget(et_h, 0)
        fila_h.addWidget(self.bar_humedad, 1)
        fila_h.addWidget(self.humedad_pct, 0)
        L.addLayout(fila_h)

        fila_pron = QHBoxLayout()
        fila_pron.setSpacing(8)
        self.chip_hoy = self._chip("Hoy", "— / —", "📅")
        self.chip_mna = self._chip("Mañana", "— / —", "🌤️")
        self.chip_sol = self._chip("Sol", "— · —", "🌅")
        fila_pron.addWidget(self.chip_hoy["wrap"])
        fila_pron.addWidget(self.chip_mna["wrap"])
        fila_pron.addWidget(self.chip_sol["wrap"])
        L.addLayout(fila_pron)

        self.chip_alerta = QLabel("")
        self.chip_alerta.setObjectName("chipAlerta")
        self.chip_alerta.setWordWrap(True)
        self.chip_alerta.setVisible(False)
        L.addWidget(self.chip_alerta)

        self.mapa_sol = W.MapaSol(W.LAT, W.LON)
        L.addWidget(self.mapa_sol)

        self.tarj_cita = W.TarjetaCita()
        L.addWidget(self.tarj_cita)

    @staticmethod
    def _chip(etiqueta: str, valor: str, emoji: str) -> dict[str, Any]:
        wrap = QFrame()
        wrap.setObjectName("chipClima")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(2)
        h = QHBoxLayout()
        h.setSpacing(6)
        em = QLabel(emoji)
        em.setObjectName("chipEmoji")
        et = QLabel(etiqueta.upper())
        et.setObjectName("chipEtiqueta")
        h.addWidget(em, 0)
        h.addWidget(et, 1)
        val = QLabel(valor)
        val.setObjectName("chipValor")
        v.addLayout(h)
        v.addWidget(val)
        return {"wrap": wrap, "valor": val, "etiqueta": et, "emoji": em}

    def pintar(
        self,
        d: dict[str, Any],
        *,
        aplicar_tema_global: Callable[[dict[str, str]], None],
        modo_claro: bool,
    ) -> None:
        import widget as W

        if d.get("err"):
            tema = W.tema_visual(3, True, claro_forzado=modo_claro)
            aplicar_tema_global(tema)
            self.icono.setText("—")
            self.temp.setText("—")
            self.estado_txt.setText("Sin conexión o error al cargar.")
            self.chip_hum["valor"].setText("—")
            self.chip_sens["valor"].setText("—")
            self.chip_viento["valor"].setText("—")
            self.humedad_pct.setText("—")
            self.bar_humedad.setValue(0)
            self.chip_hoy["valor"].setText("— / —")
            self.chip_mna["valor"].setText("— / —")
            self.chip_sol["valor"].setText("— · —")
            return

        code = int(d.get("code") or 0)
        es_dia = bool(d.get("es_dia", True))
        tema = W.tema_visual(code, es_dia, claro_forzado=modo_claro)
        aplicar_tema_global(tema)

        self.fecha.setText(W.texto_fecha_es())
        t = d.get("t")
        self.temp.setText(f"{t:.0f}°" if isinstance(t, (int, float)) else "—")
        self.ciudad.setText(W.CIUDAD.upper())
        self.icono.setText(W.wmo_emoji(code))
        self.estado_txt.setText(W.wmo_txt(code))

        ap = d.get("apparent")
        self.chip_sens["valor"].setText(
            f"{ap:.0f}°" if isinstance(ap, (int, float)) else "—"
        )

        hum = d.get("hum")
        if hum is not None:
            self.chip_hum["valor"].setText(f"{int(hum)} %")
            self.humedad_pct.setText(f"{int(hum)} %")
            self.bar_humedad.setValue(int(hum))
        else:
            self.chip_hum["valor"].setText("—")
            self.humedad_pct.setText("—")
            self.bar_humedad.setValue(0)

        wkmh = d.get("wind_kmh")
        wd = d.get("wind_deg")
        if wkmh is not None:
            self.chip_viento["valor"].setText(
                f"{wkmh:.0f} km/h {W.rosa_viento(wd)}".strip()
            )
        else:
            self.chip_viento["valor"].setText("—")

        def _mm(mn: Any, mx: Any) -> str:
            if mn is None and mx is None:
                return "— / —"
            mn_t = f"{float(mn):.0f}°" if isinstance(mn, (int, float)) else "—"
            mx_t = f"{float(mx):.0f}°" if isinstance(mx, (int, float)) else "—"
            return f"{mn_t} / {mx_t}"

        self.chip_hoy["valor"].setText(_mm(d.get("tmin_hoy"), d.get("tmax_hoy")))
        self.chip_mna["valor"].setText(_mm(d.get("tmin_mna"), d.get("tmax_mna")))

        def _hh(iso: Any) -> str:
            if not isinstance(iso, str):
                return "—"
            try:
                return datetime.fromisoformat(iso).strftime("%H:%M")
            except ValueError:
                return iso[-5:] if len(iso) >= 5 else "—"

        sr = _hh(d.get("sunrise_hoy"))
        ss = _hh(d.get("sunset_hoy"))
        self.chip_sol["valor"].setText(f"{sr} · {ss}")


class PanelDeportes(QWidget):
    """Cuadrícula de tarjetas por equipo / F1."""

    def __init__(
        self,
        get_equipos: Callable[[], list[dict[str, str]]],
        on_tarjeta_clic: Callable[[TarjetaPartido], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panelDeportes")
        self.setAutoFillBackground(False)
        self._get_equipos = get_equipos
        self._on_tarjeta_clic = on_tarjeta_clic
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self.tarjetas_deportes: dict[str, TarjetaPartido] = {}
        self.reconstruir()

    def reconstruir(self) -> None:
        while self._lay.count():
            it = self._lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self.tarjetas_deportes = {}
        equipos = self._get_equipos()
        filas: list[list[TarjetaPartido]] = []
        for idx, eq in enumerate(equipos):
            liga = eq.get("liga", "")
            nombre = eq.get("nombre") or (
                "Fórmula 1"
                if liga == "f1"
                else LIGAS_TSD.get(liga, {}).get("nombre", "—")
            )
            emoji = (
                "🏎️"
                if liga == "f1"
                else LIGAS_TSD.get(liga, {}).get("emoji", "🏆")
            )
            tarj = TarjetaPartido(nombre, emoji)
            clave = _clave_equipo(eq, idx)
            self.tarjetas_deportes[clave] = tarj
            tarj.clic.connect(lambda t=tarj: self._on_tarjeta_clic(t))
            if idx % 2 == 0:
                filas.append([tarj])
            else:
                filas[-1].append(tarj)
        for fila in filas:
            h = QHBoxLayout()
            h.setSpacing(8)
            if len(fila) == 1:
                h.addStretch(1)
                fila[0].setMaximumWidth(360)
                h.addWidget(fila[0], 0, Qt.AlignmentFlag.AlignCenter)
                h.addStretch(1)
            else:
                for t in fila:
                    h.addWidget(t, 1)
            self._lay.addLayout(h)


class PanelMetricasEquipo(QWidget):
    """CPU / RAM / disco + frecuencia."""

    def __init__(self, parent: QWidget | None = None) -> None:
        from metricas import COLORES_SERIE
        from widget import PanelSerie

        super().__init__(parent)
        self.setObjectName("panelMetricasEquipo")
        self.setAutoFillBackground(False)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.panel_cpu = PanelSerie(
            "CPU", " %", 0, 100, COLORES_SERIE[0], altura=72, parent=self
        )
        self.panel_ram = PanelSerie(
            "RAM", " %", 0, 100, COLORES_SERIE[1], altura=72, parent=self
        )
        self.panel_disk = PanelSerie(
            "DISCO /", " %", 0, 100, COLORES_SERIE[2], altura=72, parent=self
        )
        h.addWidget(self.panel_cpu, 1)
        h.addWidget(self.panel_ram, 1)
        h.addWidget(self.panel_disk, 1)
        v.addLayout(h)
        self.lbl_freq = QLabel("CPU @ — MHz · — núcleos")
        self.lbl_freq.setObjectName("lblFreq")
        self.lbl_freq.setAlignment(Qt.AlignmentFlag.AlignRight)
        v.addWidget(self.lbl_freq)


class PanelSolarDashboard(QWidget):
    """Mapa del sistema solar + ficha de planeta."""

    def __init__(
        self,
        on_planeta: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        from sistema_solar import MapaSistemaSolar, PanelInfoPlaneta

        super().__init__(parent)
        self.setObjectName("panelSolar")
        self.setAutoFillBackground(False)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self.mapa_solar = MapaSistemaSolar()
        self.mapa_solar.planeta_clic.connect(on_planeta)
        v.addWidget(self.mapa_solar)
        self.panel_planeta = PanelInfoPlaneta()
        v.addWidget(self.panel_planeta)
        self.mapa_solar.set_seleccion("Tierra")
        self.panel_planeta.mostrar("Tierra", self.mapa_solar.posiciones)


class PanelDescargas(QFrame):
    """URL, tipo, calidad y carpeta de salida."""

    def __init__(
        self,
        cfg: dict[str, Any],
        carpeta_inicial: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panelDescargas")
        self._cfg = cfg
        self.descargando = False
        self.carpeta_desc = Path(carpeta_inicial)

        L = QVBoxLayout(self)
        L.setContentsMargins(14, 12, 14, 12)
        L.setSpacing(10)

        self.lbl_aviso = QLabel(
            "YouTube, X (Twitter) y otros sitios. "
            "Recomendado: ffmpeg + ffprobe (sudo apt install ffmpeg) "
            "para MP3 y para vídeo con la calidad elegida."
        )
        self.lbl_aviso.setObjectName("descAviso")
        self.lbl_aviso.setWordWrap(True)
        L.addWidget(self.lbl_aviso)

        self.lbl_ytdlp: QLabel | None = None
        if not yt_dlp_instalado():
            self.lbl_ytdlp = QLabel(
                "Instala dependencias: en Linux ./run.sh · en Windows run.bat"
            )
            self.lbl_ytdlp.setObjectName("descEstado")
            self.lbl_ytdlp.setWordWrap(True)
            L.addWidget(self.lbl_ytdlp)

        et_url = QLabel("ENLACE")
        et_url.setObjectName("descEt")
        L.addWidget(et_url)
        self.ed_url = QLineEdit()
        self.ed_url.setObjectName("descUrl")
        self.ed_url.setPlaceholderText(
            "https://www.youtube.com/…  o  https://x.com/…"
        )
        L.addWidget(self.ed_url)

        fila = QHBoxLayout()
        fila.setSpacing(10)
        lab_tipo = QLabel("Tipo")
        lab_tipo.setObjectName("descEt")
        self.cb_tipo = QComboBox()
        self.cb_tipo.setObjectName("descCombo")
        self.cb_tipo.addItems(["Solo audio (MP3)", "Video (MP4)"])
        self.lab_calidad = QLabel("Calidad video")
        self.lab_calidad.setObjectName("descEt")
        self.cb_calidad = QComboBox()
        self.cb_calidad.setObjectName("descCombo")
        for etiqueta, _ in CALIDADES_VIDEO:
            self.cb_calidad.addItem(etiqueta)
        fila.addWidget(lab_tipo, 0)
        fila.addWidget(self.cb_tipo, 1)
        fila.addWidget(self.lab_calidad, 0)
        fila.addWidget(self.cb_calidad, 1)
        L.addLayout(fila)

        def _toggle_calidad(_i: int) -> None:
            es_video = self.cb_tipo.currentIndex() == 1
            self.cb_calidad.setEnabled(es_video)
            self.lab_calidad.setEnabled(es_video)

        self.cb_tipo.currentIndexChanged.connect(_toggle_calidad)
        _toggle_calidad(0)

        carp_row = QHBoxLayout()
        carp_row.setSpacing(8)
        self.lbl_carpeta = QLabel(str(self.carpeta_desc))
        self.lbl_carpeta.setObjectName("descEstado")
        self.lbl_carpeta.setWordWrap(True)
        self.btn_carpeta = QPushButton("Carpeta…")
        self.btn_carpeta.setObjectName("descBtn")
        carp_row.addWidget(self.lbl_carpeta, 1)
        carp_row.addWidget(self.btn_carpeta, 0)
        L.addLayout(carp_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_descargar = QPushButton("Descargar")
        self.btn_descargar.setObjectName("descBtnPri")
        btn_row.addWidget(self.btn_descargar)
        L.addLayout(btn_row)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setObjectName("descEstado")
        self.lbl_estado.setWordWrap(True)
        L.addWidget(self.lbl_estado)


class PanelNoticiasFeed(QFrame):
    """Titulares Infobae / Fox."""

    def __init__(
        self,
        on_actualizar: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panelNoticias")
        self.ultimos_datos: dict[str, Any] = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)

        av = QLabel(
            "Top 2 de Infobae y Fox News. "
            "Los titulares de Fox News se traducen al español al cargar."
        )
        av.setObjectName("noticiaAviso")
        av.setWordWrap(True)
        v.addWidget(av)

        ibh = QLabel("INFOBAE")
        ibh.setObjectName("noticiaFuente")
        v.addWidget(ibh)
        self.ib_rows: list[QLabel] = []
        for _ in range(2):
            lb = QLabel("Cargando…")
            lb.setObjectName("noticiaItem")
            lb.setWordWrap(True)
            lb.setOpenExternalLinks(True)
            lb.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            self.ib_rows.append(lb)
            v.addWidget(lb)

        fxh = QLabel("FOX NEWS · TRADUCIDO")
        fxh.setObjectName("noticiaFuente")
        v.addWidget(fxh)
        self.fx_rows: list[QLabel] = []
        for _ in range(2):
            lb = QLabel("Cargando…")
            lb.setObjectName("noticiaItem")
            lb.setWordWrap(True)
            lb.setOpenExternalLinks(True)
            lb.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            self.fx_rows.append(lb)
            v.addWidget(lb)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setObjectName("noticiaEstado")
        self.lbl_estado.setWordWrap(True)
        v.addWidget(self.lbl_estado)

        row_btn = QHBoxLayout()
        row_btn.addStretch(1)
        self.btn_ref = QPushButton("Actualizar ahora")
        self.btn_ref.setObjectName("noticiaBtn")
        self.btn_ref.clicked.connect(on_actualizar)
        row_btn.addWidget(self.btn_ref)
        v.addLayout(row_btn)

    def aplicar_datos(self, d: dict[str, Any], acento: str) -> None:
        self.ultimos_datos = dict(d)

        def enlace(it: dict[str, str]) -> str:
            t = html.escape(it.get("titulo", "") or "—")
            u = html.escape(it.get("url", "#") or "#")
            return (
                f'<a href="{u}" style="color:{acento}; text-decoration:none;">'
                f"<span style='font-weight:600;'>{t}</span></a>"
            )

        for i, lb in enumerate(self.ib_rows):
            items = d.get("infobae") or []
            if i < len(items):
                lb.setText(enlace(items[i]))
                lb.setVisible(True)
            else:
                lb.setVisible(False)
        for i, lb in enumerate(self.fx_rows):
            items = d.get("fox") or []
            if i < len(items):
                lb.setText(enlace(items[i]))
                lb.setVisible(True)
            else:
                lb.setVisible(False)
        err = d.get("err")
        self.lbl_estado.setText(str(err) if err else "")

