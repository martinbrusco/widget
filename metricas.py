"""Métricas locales y paneles de serie estilo Grafana (pyqtgraph)."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from collections import deque
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psutil
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

# Paleta tipo Grafana / dark dashboard
COLORES_SERIE = [
    "#FF9830",
    "#5794F2",
    "#73BF69",
    "#F2495C",
    "#B877D9",
    "#FFEE52",
    "#56A64B",
    "#E0B400",
]


def _temperaturas_sysfs() -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    base = "/sys/class/thermal"
    try:
        for name in sorted(os.listdir(base)):
            if not name.startswith("thermal_zone"):
                continue
            z = os.path.join(base, name)
            try:
                with open(os.path.join(z, "type"), encoding="utf-8") as f:
                    typ = f.read().strip() or name
                with open(os.path.join(z, "temp"), encoding="utf-8") as f:
                    mc = int(f.read().strip())
                out.append((typ, mc / 1000.0))
            except (OSError, ValueError):
                continue
    except OSError:
        pass
    return out


def _temperaturas_psutil() -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    try:
        st = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return out
    if not st:
        return out
    for chip, entries in st.items():
        for i, e in enumerate(entries or []):
            if e.current is None:
                continue
            label = e.label or str(i)
            out.append((f"{chip} · {label}", float(e.current)))
    return out


def notificar_escritorio(
    titulo: str,
    cuerpo: str,
    *,
    urgencia: str = "normal",
    icono: str = "dialog-warning",
    app: str = "Clima Widget",
) -> bool:
    """Envia una notificación del escritorio. Devuelve True si se envió.

    Intenta `notify-send` y, si no, libnotify vía D-Bus.
    """
    cmd = shutil.which("notify-send")
    if cmd:
        try:
            subprocess.run(
                [
                    cmd,
                    "--app-name",
                    app,
                    "-u",
                    urgencia,
                    "-i",
                    icono,
                    titulo,
                    cuerpo,
                ],
                timeout=5,
                capture_output=True,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        import dbus  # type: ignore[import-not-found]

        bus = dbus.SessionBus()
        proxy = bus.get_object(
            "org.freedesktop.Notifications", "/org/freedesktop/Notifications"
        )
        iface = dbus.Interface(proxy, "org.freedesktop.Notifications")
        urg_int = {"low": 0, "normal": 1, "critical": 2}.get(urgencia, 1)
        iface.Notify(
            app,
            0,
            icono,
            titulo,
            cuerpo,
            [],
            {"urgency": dbus.Byte(urg_int)},
            -1,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def fmt_seg(s: float) -> str:
    s = int(max(0, s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


def fmt_bytes(n: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    f = float(n)
    i = 0
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.1f} {units[i]}"


UMBRALES_TEMP: dict[str, tuple[float, float]] = {
    "cpu": (82.0, 92.0),
    "gpu": (80.0, 90.0),
    "nvme": (62.0, 75.0),
    "disco": (55.0, 65.0),
    "bateria": (45.0, 55.0),
    "wifi": (75.0, 85.0),
    "placa": (75.0, 88.0),
}
UMBRAL_DEFAULT: tuple[float, float] = (78.0, 88.0)


def _clave_sensor(nombre: str) -> str:
    n = (nombre or "").lower()
    if any(k in n for k in ("cpu", "package id", "core ", "tctl", "tdie", "k10", "x86_pkg", "coretemp")):
        return "cpu"
    if any(k in n for k in ("gpu", "amdgpu", "nvidia", "edge", "junction", "vga")):
        return "gpu"
    if "nvme" in n or "composite" in n:
        return "nvme"
    if any(k in n for k in ("disco", "disk", "hdd", "ssd")):
        return "disco"
    if any(k in n for k in ("bateria", "battery", "bat")):
        return "bateria"
    if any(k in n for k in ("wifi", "iwlwifi", "wlan", "ath")):
        return "wifi"
    if any(k in n for k in ("placa", "acpitz", "thinkpad", "pch", "motherboard")):
        return "placa"
    return "otro"


def umbrales_temperatura(nombre: str) -> tuple[float, float]:
    return UMBRALES_TEMP.get(_clave_sensor(nombre), UMBRAL_DEFAULT)


def evaluar_temperaturas(
    items: list[tuple[str, float]],
) -> list[dict[str, Any]]:
    """Devuelve lista de alertas {nombre, valor, umbral_warn, umbral_crit, nivel, clave}."""
    out: list[dict[str, Any]] = []
    for nombre, valor in items:
        try:
            v = float(valor)
        except (TypeError, ValueError):
            continue
        warn, crit = umbrales_temperatura(nombre)
        if v >= crit:
            nivel = "crit"
        elif v >= warn:
            nivel = "warn"
        else:
            continue
        out.append(
            {
                "nombre": nombre,
                "valor": v,
                "warn": warn,
                "crit": crit,
                "nivel": nivel,
                "clave": _clave_sensor(nombre),
            }
        )
    out.sort(key=lambda a: (-({"crit": 2, "warn": 1}.get(a["nivel"], 0)), -a["valor"]))
    return out


def filtrar_temperaturas(items: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Reduce sensores redundantes a ~4–6 categorías legibles."""
    keepers: dict[str, tuple[str, float]] = {}
    cores: list[float] = []
    for nombre, val in items:
        n = nombre.lower()
        if "package id" in n or "x86_pkg_temp" in n or "pch" in n and False:
            keepers["cpu"] = ("CPU", val)
        elif n.startswith("core ") or " · core " in n:
            cores.append(val)
        elif "tctl" in n or "tdie" in n:
            keepers.setdefault("cpu", ("CPU", val))
        elif "nvme" in n and "composite" in n:
            keepers["nvme"] = ("Disco NVMe", val)
        elif "nvme" in n:
            keepers.setdefault("nvme", ("Disco NVMe", val))
        elif "amdgpu" in n or "nouveau" in n or n.endswith(" gpu") or "gpu_thermal" in n:
            if "edge" in n or "junction" in n:
                keepers["gpu"] = ("GPU", val)
            else:
                keepers.setdefault("gpu", ("GPU", val))
        elif "iwlwifi" in n or "wlan" in n or "wifi" in n:
            keepers.setdefault("wifi", ("Wi-Fi", val))
        elif "acpitz" in n or "thermal_zone" in n:
            keepers.setdefault("placa", ("Placa base", val))
        elif "battery" in n or "bat0" in n or "bat1" in n:
            keepers.setdefault("bateria", ("Batería", val))
        elif any(k in n for k in ("ssd", "sda", "hdd", "disk")):
            keepers.setdefault("disco", ("Disco", val))
        else:
            etiqueta = nombre.split(" · ")[-1] if " · " in nombre else nombre
            keepers.setdefault(f"otro_{etiqueta}", (etiqueta[:14], val))

    if cores and "cpu" not in keepers:
        keepers["cpu"] = ("CPU", sum(cores) / len(cores))

    OTROS_DESCARTAR = ("int3400", "sen1", "tcpu", "pch", "therma", "x86_pkg")
    orden = ("cpu", "gpu", "nvme", "disco", "placa", "wifi", "bateria")
    out: list[tuple[str, float]] = []
    for clave in orden:
        if clave in keepers:
            out.append(keepers[clave])
    if len(out) < 3:
        for k, v in keepers.items():
            if not k.startswith("otro_"):
                continue
            etiqueta_lower = v[0].lower()
            if any(d in etiqueta_lower for d in OTROS_DESCARTAR):
                continue
            out.append(v)
            if len(out) >= 5:
                break
    return out[:5]


def recolectar_metricas() -> dict[str, Any]:
    """Una muestra instantánea: CPU, RAM, disco y temperaturas disponibles."""
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    temps = _temperaturas_sysfs()
    seen = {n for n, _ in temps}
    for n, v in _temperaturas_psutil():
        if n in seen:
            continue
        temps.append((n, v))
        seen.add(n)
    return {
        "cpu_pct": float(psutil.cpu_percent(interval=None)),
        "ram_pct": float(vm.percent),
        "ram_used_gb": vm.used / (1024**3),
        "ram_total_gb": vm.total / (1024**3),
        "disk_pct": float(du.percent),
        "disk_free_gb": du.free / (1024**3),
        "temps": temps,
    }


def _leer_archivo(ruta: str) -> str:
    try:
        with open(ruta, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _clasificar_bateria(nombre_id: str, modelo: str) -> tuple[str, str]:
    """Devuelve (tipo, emoji) según pistas en el nombre/modelo."""
    txt = f"{nombre_id} {modelo}".lower()
    if any(k in txt for k in ("mouse", "raton", "ratón", "mx-master", "mx anywhere")):
        return ("mouse", "🖱")
    if any(
        k in txt
        for k in ("headset", "headphone", "earbud", "earphone", "buds", "airpods", "audio")
    ):
        return ("audio", "🎧")
    if any(k in txt for k in ("keyboard", "teclado", "kb", "magic key")):
        return ("teclado", "⌨️")
    if any(k in txt for k in ("controller", "joypad", "gamepad", "dualshock", "xbox")):
        return ("gamepad", "🎮")
    if nombre_id.startswith("hid-") or "bluetooth" in txt:
        return ("bt", "📱")
    return ("laptop", "💻")


def recolectar_baterias() -> list[dict[str, Any]]:
    """Baterías del sistema (laptop) y dispositivos Bluetooth.

    Lee `/sys/class/power_supply/`. Devuelve cada dispositivo con
    `id`, `nombre`, `pct`, `status`, `tipo` y `emoji`.
    """
    base = "/sys/class/power_supply"
    out: list[dict[str, Any]] = []
    try:
        entradas = sorted(os.listdir(base))
    except OSError:
        entradas = []
    for nombre in entradas:
        ruta = os.path.join(base, nombre)
        typ = _leer_archivo(os.path.join(ruta, "type"))
        if typ != "Battery":
            continue
        cap_txt = _leer_archivo(os.path.join(ruta, "capacity"))
        if not cap_txt:
            continue
        try:
            pct = max(0, min(100, int(cap_txt)))
        except ValueError:
            continue
        status = _leer_archivo(os.path.join(ruta, "status")) or "Unknown"
        modelo = (
            _leer_archivo(os.path.join(ruta, "model_name"))
            or _leer_archivo(os.path.join(ruta, "manufacturer"))
            or ""
        )
        tipo, emoji = _clasificar_bateria(nombre, modelo)
        if tipo == "laptop":
            etiqueta = "Portátil"
        else:
            etiqueta = (modelo or nombre).replace("_", " ").strip()
            if etiqueta.lower().startswith("hid-"):
                etiqueta = "Dispositivo BT"
        out.append(
            {
                "id": nombre,
                "nombre": etiqueta[:28],
                "pct": pct,
                "status": status,
                "tipo": tipo,
                "emoji": emoji,
            }
        )
    if not out:
        try:
            b = psutil.sensors_battery()
        except (AttributeError, OSError):
            b = None
        if b is not None:
            out.append(
                {
                    "id": "psutil",
                    "nombre": "Portátil",
                    "pct": int(b.percent),
                    "status": "Charging" if b.power_plugged else "Discharging",
                    "tipo": "laptop",
                    "emoji": "💻",
                }
            )
    out.sort(key=lambda x: (x["tipo"] != "laptop", x["nombre"].lower()))
    return out


def _interfaz_wifi() -> str | None:
    try:
        for n in sorted(os.listdir("/sys/class/net")):
            if os.path.isdir(os.path.join("/sys/class/net", n, "wireless")):
                return n
    except OSError:
        pass
    return None


def _ssid_de(iface: str) -> str:
    cmd = shutil.which("iwgetid")
    if cmd:
        try:
            out = subprocess.check_output(
                [cmd, "-r", iface], timeout=1.0, stderr=subprocess.DEVNULL
            )
            s = out.decode("utf-8", "replace").strip()
            if s:
                return s
        except (OSError, subprocess.SubprocessError):
            pass
    nmcli = shutil.which("nmcli")
    if nmcli:
        try:
            out = subprocess.check_output(
                [nmcli, "-t", "-f", "active,ssid", "dev", "wifi"],
                timeout=1.0,
                stderr=subprocess.DEVNULL,
            )
            for ln in out.decode("utf-8", "replace").splitlines():
                if ln.startswith("yes:"):
                    return ln.split(":", 1)[1] or ""
        except (OSError, subprocess.SubprocessError):
            pass
    return ""


class MonitorRed:
    """Captura tráfico de red (Wi-Fi) y mantiene acumulado por sesión."""

    def __init__(self) -> None:
        snap = self._snap()
        self._inicio = snap
        self._prev = snap
        self._prev_t = time.time()
        self._t0 = time.time()
        self._ping_cache: float | None = None
        self._ping_t = 0.0
        self._iplocal_cache: str | None = None
        self._iplocal_t = 0.0

    def _snap(self) -> dict[str, Any]:
        iface = _interfaz_wifi()
        rx = tx = 0
        if iface:
            try:
                stats = psutil.net_io_counters(pernic=True).get(iface)
            except (AttributeError, OSError):
                stats = None
            if stats is not None:
                rx = int(stats.bytes_recv)
                tx = int(stats.bytes_sent)
        return {"iface": iface, "rx": rx, "tx": tx}

    def tick(self) -> dict[str, Any] | None:
        now = self._snap()
        if not now["iface"]:
            return None
        ahora = time.time()
        dt = max(0.05, ahora - self._prev_t)
        rx_rate = max(0.0, (now["rx"] - self._prev["rx"]) / dt)
        tx_rate = max(0.0, (now["tx"] - self._prev["tx"]) / dt)
        if (
            now["iface"] != self._inicio["iface"]
            or now["rx"] < self._inicio["rx"]
            or now["tx"] < self._inicio["tx"]
        ):
            self._inicio = {"iface": now["iface"], "rx": now["rx"], "tx": now["tx"]}
        sesion_rx = max(0, now["rx"] - self._inicio["rx"])
        sesion_tx = max(0, now["tx"] - self._inicio["tx"])
        self._prev = now
        self._prev_t = ahora
        if ahora - self._iplocal_t > 30:
            self._iplocal_cache = ip_local(now["iface"])
            self._iplocal_t = ahora
        return {
            "iface": now["iface"],
            "ssid": _ssid_de(now["iface"]),
            "rx_rate": rx_rate,
            "tx_rate": tx_rate,
            "sesion_rx": sesion_rx,
            "sesion_tx": sesion_tx,
            "uptime": ahora - self._t0,
            "dbm": signal_dbm(now["iface"]),
            "ip_local": self._iplocal_cache,
            "ip_pub": _ipp_cache.v,
            "ping_ms": self._ping_cache,
        }

    def actualizar_ping(self) -> None:
        """Llamar en hilo aparte cada ~5s."""
        self._ping_cache = ping_ms()
        self._ping_t = time.time()


class MonitorApps:
    """Top de apps por CPU% y RAM agregadas por nombre de proceso."""

    EXCLUIR = {
        "kthreadd", "ksoftirqd", "kworker", "rcu_sched", "rcu_preempt",
        "watchdog", "swapper", "init", "systemd",
    }

    def __init__(self) -> None:
        self._procs: dict[int, psutil.Process] = {}
        self._tiempo_acum: dict[str, float] = {}
        self._t_inicio = time.time()
        self._t_anterior = self._t_inicio
        try:
            for p in psutil.process_iter():
                self._procs[p.pid] = p
                try:
                    p.cpu_percent(None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.Error, OSError):
            pass

    def tick(self) -> dict[str, dict[str, Any]]:
        cpus_logicas = max(1, psutil.cpu_count(logical=True) or 1)
        agregado: dict[str, dict[str, Any]] = {}
        nuevo: dict[int, psutil.Process] = {}
        ahora = time.time()
        dt = max(0.0, ahora - self._t_anterior)
        self._t_anterior = ahora
        try:
            iterador = psutil.process_iter(attrs=("pid", "name"))
        except psutil.Error:
            return {}
        nombres_vivos: set[str] = set()
        for p in iterador:
            try:
                pid = p.pid
                obj = self._procs.get(pid)
                if obj is None:
                    obj = p
                    try:
                        obj.cpu_percent(None)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                    nuevo[pid] = obj
                    continue
                cpu = float(obj.cpu_percent(None))
                rss = int(obj.memory_info().rss)
                nombre = (
                    (obj.info.get("name") if hasattr(obj, "info") else None)
                    or obj.name()
                    or "?"
                )
                if nombre in self.EXCLUIR:
                    nuevo[pid] = obj
                    continue
                d = agregado.setdefault(
                    nombre,
                    {"cpu": 0.0, "ram": 0.0, "n": 0, "pids": []},
                )
                d["cpu"] += cpu / cpus_logicas
                d["ram"] += float(rss)
                d["n"] = int(d["n"]) + 1
                d["pids"].append(pid)
                nombres_vivos.add(nombre)
                nuevo[pid] = obj
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
        self._procs = nuevo
        for nombre in nombres_vivos:
            self._tiempo_acum[nombre] = self._tiempo_acum.get(nombre, 0.0) + dt
        return agregado

    def top_n(self, n: int = 5) -> list[dict[str, Any]]:
        agg = self.tick()
        items = [
            {
                "nombre": nombre,
                "cpu_pct": round(d["cpu"], 1),
                "ram_mb": d["ram"] / (1024 * 1024),
                "n": int(d["n"]),
                "pids": list(d.get("pids") or []),
                "tiempo_s": float(self._tiempo_acum.get(nombre, 0.0)),
            }
            for nombre, d in agg.items()
        ]
        items.sort(key=lambda x: (x["cpu_pct"], x["ram_mb"]), reverse=True)
        return items[:n]


def matar_proceso(pids: list[int]) -> tuple[bool, str]:
    """Intenta terminar; usa pkexec si hace falta privilegios."""
    fallidos: list[int] = []
    for pid in pids:
        try:
            psutil.Process(pid).terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            fallidos.append(pid)
        except OSError:
            fallidos.append(pid)
    if not fallidos:
        return True, "OK"
    pkexec = shutil.which("pkexec")
    if not pkexec:
        return False, "Sin permisos"
    try:
        subprocess.run(
            [pkexec, "kill", "-9", *[str(p) for p in fallidos]],
            timeout=10,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return True, "OK"


def listar_docker() -> list[dict[str, Any]] | None:
    """Lista contenedores corriendo. Devuelve None si Docker no está accesible."""
    cmd = shutil.which("docker")
    if not cmd:
        return None
    try:
        out = subprocess.check_output(
            [
                cmd,
                "ps",
                "--no-trunc",
                "--format",
                "{{.Names}}|{{.Image}}|{{.Status}}|{{.State}}|{{.Ports}}",
            ],
            timeout=2.0,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    rows: list[dict[str, Any]] = []
    for line in out.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        rows.append(
            {
                "nombre": parts[0],
                "imagen": parts[1],
                "status": parts[2],
                "estado": parts[3].lower(),
                "puertos": parts[4] if len(parts) > 4 else "",
            }
        )
    return rows


_TURBO_INTEL = "/sys/devices/system/cpu/intel_pstate/no_turbo"
_TURBO_AMD = "/sys/devices/system/cpu/cpufreq/boost"


def estado_turbo() -> dict[str, Any] | None:
    """Detecta el archivo de control y lee el estado actual."""
    if os.path.exists(_TURBO_INTEL):
        try:
            v = _leer_archivo(_TURBO_INTEL)
            return {
                "vendor": "intel",
                "path": _TURBO_INTEL,
                "activo": v == "0",
                "raw": v,
            }
        except OSError:
            return None
    if os.path.exists(_TURBO_AMD):
        try:
            v = _leer_archivo(_TURBO_AMD)
            return {
                "vendor": "amd",
                "path": _TURBO_AMD,
                "activo": v == "1",
                "raw": v,
            }
        except OSError:
            return None
    return None


def cambiar_turbo(activar: bool) -> tuple[bool, str]:
    """Activa o desactiva Turbo Boost. Usa pkexec si el archivo no es escribible."""
    info = estado_turbo()
    if not info:
        return False, "No soportado"
    if info["vendor"] == "intel":
        valor = "0" if activar else "1"
    else:
        valor = "1" if activar else "0"
    try:
        with open(info["path"], "w", encoding="utf-8") as f:
            f.write(valor)
        return True, "OK"
    except PermissionError:
        pass
    except OSError as e:
        return False, str(e)
    pkexec = shutil.which("pkexec")
    if not pkexec:
        return False, "Necesita pkexec"
    try:
        r = subprocess.run(
            [pkexec, "sh", "-c", f"echo {valor} > {info['path']}"],
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if r.returncode == 0:
        return True, "OK"
    return False, "Cancelado o sin permisos"


_FAN_THROTTLE = "/sys/devices/platform/asus-nb-wmi/throttle_thermal_policy"
_FAN_PROFILE = "/sys/firmware/acpi/platform_profile"
_FAN_PROFILE_CHOICES = "/sys/firmware/acpi/platform_profile_choices"
_FAN_NOMBRES = {0: "Normal", 1: "Overboost", 2: "Silencioso"}

# Mapeo modo lógico (mismo que TarjetaFan: 0/1/2) ↔ valor en sysfs.
# Para platform_profile elegimos el primer alias presente entre las choices.
_PROFILE_ALIAS: dict[int, tuple[str, ...]] = {
    0: ("balanced", "balanced-performance"),
    1: ("performance", "balanced-performance"),
    2: ("quiet", "low-power", "balanced"),
}


def _profile_choices() -> list[str]:
    raw = _leer_archivo(_FAN_PROFILE_CHOICES)
    if not raw:
        return []
    return raw.strip().split()


def _profile_para_modo(modo: int) -> str | None:
    choices = _profile_choices()
    for alias in _PROFILE_ALIAS.get(modo, ()):
        if alias in choices:
            return alias
    return None


def _modo_desde_profile(valor: str) -> int | None:
    valor = (valor or "").strip().lower()
    for modo, aliases in _PROFILE_ALIAS.items():
        if valor in aliases:
            return modo
    return None


def estado_fan() -> dict[str, Any] | None:
    """Estado del modo de ventilador. Prioriza ACPI platform_profile."""
    valor: int | None = None
    fuente = ""
    detalle = ""
    if os.path.exists(_FAN_PROFILE):
        raw = _leer_archivo(_FAN_PROFILE)
        if raw is not None:
            v = _modo_desde_profile(raw)
            if v is not None:
                valor = v
                fuente = "platform_profile"
                detalle = raw.strip()
    if valor is None and os.path.exists(_FAN_THROTTLE):
        raw = _leer_archivo(_FAN_THROTTLE)
        if raw is not None:
            try:
                valor = int(raw.strip())
                fuente = "throttle_thermal_policy"
                detalle = raw.strip()
            except ValueError:
                valor = None
    if valor is None:
        return None
    rutas = []
    if os.path.exists(_FAN_PROFILE):
        rutas.append("platform_profile")
    if os.path.exists(_FAN_THROTTLE):
        rutas.append("throttle_thermal_policy")
    return {
        "valor": valor,
        "nombre": _FAN_NOMBRES.get(valor, f"Modo {valor}"),
        "fuente": fuente,
        "detalle": detalle,
        "rutas": rutas,
        "choices": _profile_choices(),
    }


def cambiar_fan(modo: int) -> tuple[bool, str]:
    """Cambia el modo de ventilador. Escribe en ambos sysfs si están.

    Verifica leyendo el valor tras escribir; si no cambia, devuelve un error
    descriptivo (la BIOS de algunos ZenBook ignora `throttle_thermal_policy`
    y solo respeta `platform_profile`, y viceversa).
    """
    if modo not in (0, 1, 2):
        return False, "Modo no válido"

    objetivos: list[tuple[str, str]] = []
    if os.path.exists(_FAN_PROFILE):
        prof = _profile_para_modo(modo)
        if prof:
            objetivos.append((_FAN_PROFILE, prof))
    if os.path.exists(_FAN_THROTTLE):
        objetivos.append((_FAN_THROTTLE, str(modo)))

    if not objetivos:
        return False, "Sin interfaces de control disponibles"

    # 1) Intentar escritura directa
    pendientes: list[tuple[str, str]] = []
    for ruta, valor in objetivos:
        try:
            with open(ruta, "w", encoding="ascii") as f:
                f.write(valor)
        except (PermissionError, OSError):
            pendientes.append((ruta, valor))

    # 2) Para los que faltaron, usar pkexec en bloque
    if pendientes:
        pkexec = shutil.which("pkexec")
        if not pkexec:
            return False, "Sin permisos y sin pkexec"
        sh = shutil.which("sh") or "/bin/sh"
        cmd = " && ".join(f"echo -n '{v}' > {r}" for r, v in pendientes)
        try:
            r = subprocess.run(
                [pkexec, sh, "-c", cmd], timeout=15, capture_output=True
            )
        except (OSError, subprocess.SubprocessError) as e:
            return False, str(e)
        if r.returncode != 0:
            return False, "Cancelado o sin permisos"

    # 3) Verificar leyendo de vuelta
    fallaron: list[str] = []
    aplicaron: list[str] = []
    for ruta, valor in objetivos:
        leido = (_leer_archivo(ruta) or "").strip().lower()
        if leido == valor.lower():
            aplicaron.append(os.path.basename(ruta))
        else:
            fallaron.append(f"{os.path.basename(ruta)}={leido or '?'}≠{valor}")
    if not aplicaron:
        return False, "Ningún sysfs aceptó el valor: " + "; ".join(fallaron)
    msg = "OK · " + ", ".join(aplicaron)
    if fallaron:
        msg += " · ignorado: " + "; ".join(fallaron)
    return True, msg


def cpu_frecuencias_mhz() -> list[int]:
    try:
        per = psutil.cpu_freq(percpu=True)
    except (AttributeError, OSError):
        return []
    if not per:
        return []
    return [int(round(f.current)) for f in per]


def cpu_freq_resumen() -> dict[str, Any]:
    fr = cpu_frecuencias_mhz()
    if not fr:
        return {"actual": 0, "max": 0, "n": 0}
    return {"actual": int(round(sum(fr) / len(fr))), "max": max(fr), "n": len(fr)}


def _gpu_nvidia() -> dict[str, Any] | None:
    cmd = shutil.which("nvidia-smi")
    if not cmd:
        return None
    try:
        out = subprocess.check_output(
            [
                cmd,
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            timeout=2.0,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    primera = out.decode("utf-8", "replace").strip().splitlines()
    if not primera:
        return None
    parts = [p.strip() for p in primera[0].split(",")]
    if len(parts) < 5:
        return None
    try:
        return {
            "vendor": "NVIDIA",
            "nombre": parts[0],
            "uso_pct": float(parts[1]),
            "vram_used_mb": float(parts[2]),
            "vram_total_mb": float(parts[3]),
            "temp_c": float(parts[4]),
        }
    except ValueError:
        return None


def _gpu_amd() -> dict[str, Any] | None:
    base = "/sys/class/drm"
    try:
        entradas = os.listdir(base)
    except OSError:
        return None
    for nombre in sorted(entradas):
        if not nombre.startswith("card") or "-" in nombre:
            continue
        d = os.path.join(base, nombre, "device")
        if not os.path.exists(os.path.join(d, "gpu_busy_percent")):
            continue
        uso = _leer_archivo(os.path.join(d, "gpu_busy_percent"))
        if not uso:
            continue
        try:
            uso_v = float(uso)
        except ValueError:
            continue
        vt = _leer_archivo(os.path.join(d, "mem_info_vram_total")) or "0"
        vu = _leer_archivo(os.path.join(d, "mem_info_vram_used")) or "0"
        try:
            vt_v = float(vt) / (1024 * 1024)
            vu_v = float(vu) / (1024 * 1024)
        except ValueError:
            vt_v = vu_v = 0.0
        temp = 0.0
        for chip, entries in (psutil.sensors_temperatures() or {}).items():
            if "amdgpu" in chip.lower():
                for e in entries or []:
                    if (e.label or "").lower() in ("edge", "junction") and e.current:
                        temp = float(e.current)
                        break
        return {
            "vendor": "AMD",
            "nombre": "AMD GPU",
            "uso_pct": uso_v,
            "vram_used_mb": vu_v,
            "vram_total_mb": vt_v,
            "temp_c": temp,
        }
    return None


def recolectar_gpu() -> dict[str, Any] | None:
    g = _gpu_nvidia()
    if g:
        return g
    return _gpu_amd()


def signal_dbm(iface: str) -> int | None:
    try:
        with open("/proc/net/wireless", encoding="utf-8") as f:
            for line in f:
                ls = line.lstrip()
                if ls.startswith(iface + ":"):
                    parts = ls.split()
                    nivel = parts[3].rstrip(".")
                    try:
                        return int(float(nivel))
                    except ValueError:
                        return None
    except OSError:
        pass
    return None


def ip_local(iface: str | None = None) -> str | None:
    try:
        addrs = psutil.net_if_addrs()
    except OSError:
        return None
    if iface and iface in addrs:
        for a in addrs[iface]:
            if getattr(a.family, "name", "") == "AF_INET" or int(a.family) == 2:
                return a.address
    for nombre, lista in addrs.items():
        if nombre == "lo":
            continue
        for a in lista:
            if getattr(a.family, "name", "") == "AF_INET" or int(a.family) == 2:
                if a.address and not a.address.startswith("127."):
                    return a.address
    return None


class _Cache:
    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self.t = 0.0
        self.v: Any = None


_ipp_cache = _Cache(ttl=600.0)


def ip_publica() -> str | None:
    if _ipp_cache.v and time.time() - _ipp_cache.t < _ipp_cache.ttl:
        return _ipp_cache.v
    for url in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://ipv4.icanhazip.com",
    ):
        try:
            req = Request(url, headers={"User-Agent": "ClimaWidget/1.0"})
            with urlopen(req, timeout=4) as r:
                txt = r.read().decode("utf-8", "replace").strip()
                if txt and len(txt) <= 45:
                    _ipp_cache.v = txt
                    _ipp_cache.t = time.time()
                    return txt
        except (OSError, URLError, HTTPError, TimeoutError):
            continue
    return None


def ping_ms(host: str = "8.8.8.8") -> float | None:
    cmd = shutil.which("ping")
    if not cmd:
        return None
    try:
        out = subprocess.check_output(
            [cmd, "-c", "1", "-W", "2", host],
            timeout=3.0,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"time=([0-9.]+)", out.decode("utf-8", "replace"))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def stats_docker() -> dict[str, dict[str, Any]]:
    cmd = shutil.which("docker")
    if not cmd:
        return {}
    try:
        out = subprocess.check_output(
            [
                cmd,
                "stats",
                "--no-stream",
                "--format",
                "{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}|{{.MemUsage}}",
            ],
            timeout=3.0,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    res: dict[str, dict[str, Any]] = {}
    for ln in out.decode("utf-8", "replace").splitlines():
        ps = ln.split("|")
        if len(ps) < 4:
            continue
        try:
            cpu = float(ps[1].rstrip("%")) if ps[1].rstrip("%") else 0.0
        except ValueError:
            cpu = 0.0
        try:
            mem = float(ps[2].rstrip("%")) if ps[2].rstrip("%") else 0.0
        except ValueError:
            mem = 0.0
        res[ps[0]] = {"cpu_pct": cpu, "mem_pct": mem, "mem_uso": ps[3]}
    return res


def accion_docker(nombre: str, accion: str) -> tuple[bool, str]:
    cmd = shutil.which("docker")
    if not cmd:
        return False, "Docker no instalado"
    if accion not in ("start", "stop", "restart"):
        return False, "Acción no válida"
    try:
        r = subprocess.run(
            [cmd, accion, nombre], timeout=15, capture_output=True
        )
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if r.returncode == 0:
        return True, "OK"
    return False, r.stderr.decode("utf-8", "replace")[:80]


class PanelSerie(QFrame):
    """Gráfico de línea con relleno bajo la curva, rejilla suave y valor actual."""

    def __init__(
        self,
        titulo: str,
        sufijo_valor: str,
        y_min: float,
        y_max: float,
        color_hex: str,
        altura: int = 108,
        maxlen: int = 90,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panelSerie")
        self._sufijo = sufijo_valor
        self._y_min = y_min
        self._y_max = y_max
        self._color = color_hex
        self._buf: deque[float] = deque(maxlen=maxlen)
        self._es_temp = sufijo_valor == "°C"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._tit = QLabel(titulo.upper())
        self._tit.setObjectName("panelTitulo")
        self._val = QLabel("—")
        self._val.setObjectName("panelValor")
        self._val.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        head.addWidget(self._tit, 1)
        head.addWidget(self._val, 0)
        lay.addLayout(head)

        self._plot = pg.PlotWidget()
        self._plot.setFixedHeight(altura)
        self._plot.setMenuEnabled(False)
        self._plot.hideButtons()
        self._plot.showGrid(x=True, y=True, alpha=0.14)
        pi = self._plot.getPlotItem()
        pi.showAxis("left", False)
        pi.showAxis("bottom", False)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self._plot.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self._plot.setYRange(y_min, y_max, padding=0.02)
        c = QColor(color_hex)
        pen = pg.mkPen(color=c, width=2)
        brush = pg.mkBrush(c.red(), c.green(), c.blue(), 55)
        self._curve = self._plot.plot([], [], pen=pen, fillLevel=y_min, brush=brush)
        self._plot.setBackground((0, 0, 0, 0))
        lay.addWidget(self._plot)

    def set_rango_y(self, y_min: float, y_max: float) -> None:
        self._y_min = y_min
        self._y_max = y_max
        self._plot.setYRange(y_min, y_max, padding=0.02)
        c = QColor(self._color)
        brush = pg.mkBrush(c.red(), c.green(), c.blue(), 55)
        self._curve.opts["fillLevel"] = y_min
        self._curve.setBrush(brush)

    def set_color(self, color_hex: str) -> None:
        self._color = color_hex
        c = QColor(color_hex)
        self._curve.setPen(pg.mkPen(color=c, width=2))
        self._curve.setBrush(pg.mkBrush(c.red(), c.green(), c.blue(), 55))

    def empujar(self, v: float) -> None:
        self._buf.append(v)
        xs = list(range(len(self._buf)))
        ys = list(self._buf)
        self._curve.setData(xs, ys)
        self._val.setText(f"{v:.1f}{self._sufijo}")
        n = len(self._buf)
        if self._es_temp and ys:
            lo = min(min(ys), 35.0)
            hi = max(max(ys), 55.0)
            pad = max(2.0, (hi - lo) * 0.12)
            y0 = lo - pad
            y1 = hi + pad
            self._plot.setYRange(y0, y1, padding=0.02)
            self._curve.opts["fillLevel"] = y0
        else:
            self._plot.setYRange(self._y_min, self._y_max, padding=0.02)
            self._curve.opts["fillLevel"] = self._y_min
        if n <= 1:
            self._plot.setXRange(0, 1)
        else:
            self._plot.setXRange(max(0, n - 60), n - 1)

    def aplicar_texto_tema(self, mut: str, sec: str) -> None:
        self._tit.setStyleSheet(
            f"color: {mut}; font-size: 9px; font-weight: 700; letter-spacing: 0.16em;"
        )
        self._val.setStyleSheet(
            f"color: {sec}; font-size: 13px; font-weight: 600;"
        )

    def set_tool_tip_valor(self, texto: str) -> None:
        self._val.setToolTip(texto)


class PanelMultiSerie(QFrame):
    """Una gráfica con varias curvas + leyenda compacta debajo (todas las temps en una)."""

    def __init__(
        self,
        titulo: str,
        sufijo_valor: str,
        y_min: float,
        y_max: float,
        altura: int = 130,
        maxlen: int = 120,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panelSerie")
        self._sufijo = sufijo_valor
        self._y_min = y_min
        self._y_max = y_max
        self._maxlen = maxlen
        self._paleta = list(COLORES_SERIE)
        self._series: dict[str, dict[str, Any]] = {}
        self._seleccion: str | None = None
        self._mut = "rgba(255,255,255,0.55)"
        self._sec = "rgba(255,255,255,0.85)"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._tit = QLabel(titulo.upper())
        self._tit.setObjectName("panelTitulo")
        self._val = QLabel("—")
        self._val.setObjectName("panelValor")
        self._val.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        head.addWidget(self._tit, 1)
        head.addWidget(self._val, 0)
        lay.addLayout(head)

        self._plot = pg.PlotWidget()
        self._plot.setFixedHeight(altura)
        self._plot.setMenuEnabled(False)
        self._plot.hideButtons()
        self._plot.showGrid(x=True, y=True, alpha=0.14)
        pi = self._plot.getPlotItem()
        pi.showAxis("left", False)
        pi.showAxis("bottom", False)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self._plot.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self._plot.setYRange(y_min, y_max, padding=0.02)
        self._plot.setBackground((0, 0, 0, 0))
        lay.addWidget(self._plot)

        self._leyenda_host = QFrame()
        self._leyenda_host.setObjectName("leyendaHost")
        self._leyenda = QGridLayout(self._leyenda_host)
        self._leyenda.setContentsMargins(2, 2, 2, 2)
        self._leyenda.setHorizontalSpacing(10)
        self._leyenda.setVerticalSpacing(4)
        lay.addWidget(self._leyenda_host)

    def actualizar(self, datos: list[tuple[str, float]]) -> None:
        for nombre, _ in datos:
            if nombre not in self._series:
                idx = len(self._series)
                color = self._paleta[idx % len(self._paleta)]
                c = QColor(color)
                pen = pg.mkPen(color=c, width=2)
                curve = self._plot.plot([], [], pen=pen)
                buf: deque[float] = deque(maxlen=self._maxlen)
                self._series[nombre] = {
                    "curve": curve,
                    "buf": buf,
                    "color": color,
                    "chip": None,
                    "dot": None,
                    "label": None,
                }
                self._añadir_leyenda(idx, nombre, color)

        for nombre, valor in datos:
            s = self._series.get(nombre)
            if s is None:
                continue
            s["buf"].append(float(valor))

        self._refrescar_curvas()

    def _refrescar_curvas(self) -> None:
        sel = self._seleccion if self._seleccion in self._series else None
        all_y: list[float] = []
        for nombre, s in self._series.items():
            buf = s["buf"]
            xs = list(range(len(buf)))
            visible = sel is None or sel == nombre
            s["curve"].setVisible(visible)
            ancho = 3 if sel == nombre else 2
            s["curve"].setPen(pg.mkPen(color=QColor(s["color"]), width=ancho))
            s["curve"].setData(xs, list(buf))
            if visible:
                all_y.extend(buf)
            self._actualizar_estilo_chip(s, sel == nombre)

        if all_y:
            lo = min(min(all_y), float(self._y_min))
            hi = max(max(all_y), float(self._y_max))
            if sel is not None:
                lo_real = min(all_y)
                hi_real = max(all_y)
                rango = max(0.5, hi_real - lo_real)
                pad = rango * 0.18
                lo = lo_real - pad
                hi = hi_real + pad
            else:
                pad = max(2.0, (hi - lo) * 0.12)
                lo -= pad
                hi += pad
            self._plot.setYRange(lo, hi, padding=0.02)
        n_max = max((len(s["buf"]) for s in self._series.values()), default=1)
        if n_max <= 1:
            self._plot.setXRange(0, 1)
        else:
            ventana = 30 if sel is not None else 60
            self._plot.setXRange(max(0, n_max - ventana), n_max - 1)

        if sel is not None and self._series[sel]["buf"]:
            actual = self._series[sel]["buf"][-1]
            self._val.setText(
                f"{sel} · {actual:.1f}{self._sufijo}"
            )
        else:
            actuales = [s["buf"][-1] for s in self._series.values() if s["buf"]]
            if actuales:
                self._val.setText(f"máx {max(actuales):.1f}{self._sufijo}")

    def _toggle_serie(self, nombre: str) -> None:
        if self._seleccion == nombre:
            self._seleccion = None
        else:
            self._seleccion = nombre
        self._refrescar_curvas()

    def _añadir_leyenda(self, idx: int, nombre: str, color: str) -> None:
        et = nombre if len(nombre) <= 22 else nombre[:20] + "…"
        chip = QFrame()
        chip.setObjectName("chipLeyenda")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        h = QHBoxLayout(chip)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(6)
        dot = QFrame()
        dot.setObjectName("dotLeyenda")
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(
            f"background:{color}; border-radius:4px; border: none;"
        )
        lb = QLabel(et)
        lb.setObjectName("leyendaTexto")
        lb.setToolTip(f"{nombre}\nClic para aislar / restaurar todas")
        h.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(lb, 1, Qt.AlignmentFlag.AlignVCenter)

        def _click(_ev, nm=nombre):
            self._toggle_serie(nm)

        chip.mousePressEvent = _click  # type: ignore[assignment]
        fila = idx // 2
        col = idx % 2
        self._leyenda.addWidget(chip, fila, col)
        s = self._series[nombre]
        s["chip"] = chip
        s["dot"] = dot
        s["label"] = lb
        self._actualizar_estilo_chip(s, False)

    def _actualizar_estilo_chip(self, s: dict[str, Any], activo: bool) -> None:
        chip = s.get("chip")
        lb = s.get("label")
        if chip is None or lb is None:
            return
        if self._seleccion is None:
            color_txt = self._mut
            bg = "transparent"
            borde = "transparent"
        elif activo:
            color_txt = self._sec
            bg = "rgba(255,255,255,0.10)"
            borde = "rgba(255,255,255,0.18)"
        else:
            color_txt = "rgba(255,255,255,0.30)"
            bg = "transparent"
            borde = "transparent"
        chip.setStyleSheet(
            f"""
            QFrame#chipLeyenda {{
                background: {bg};
                border: 1px solid {borde};
                border-radius: 8px;
            }}
            QLabel#leyendaTexto {{
                color: {color_txt};
                font-size: 10px;
                font-weight: {700 if activo else 500};
            }}
            """
        )

    def aplicar_texto_tema(self, mut: str, sec: str) -> None:
        self._mut = mut
        self._sec = sec
        self._tit.setStyleSheet(
            f"color: {mut}; font-size: 9px; font-weight: 700; letter-spacing: 0.16em;"
        )
        self._val.setStyleSheet(
            f"color: {sec}; font-size: 13px; font-weight: 600;"
        )
        for nombre, s in self._series.items():
            self._actualizar_estilo_chip(s, nombre == self._seleccion)

    def numero_series(self) -> int:
        return len(self._series)
