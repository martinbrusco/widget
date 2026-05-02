#!/usr/bin/env python3
"""Diagnóstico interactivo del modo de ventilador.

Uso:
    python3 test_fan.py [silencioso|normal|overboost]

Sin argumentos solo informa; con argumento intenta cambiar (te pedirá
contraseña por pkexec) y verifica que se haya aplicado.
"""

from __future__ import annotations

import sys
import time

import metricas


def _imprimir(estado):
    if not estado:
        print("✗ No se detecta ninguna interfaz de control de ventilador")
        return
    print(f"  valor lógico: {estado['valor']} ({estado['nombre']})")
    print(f"  fuente:       {estado['fuente']}")
    print(f"  sysfs:        {estado['detalle']}")
    print(f"  rutas:        {', '.join(estado['rutas'])}")
    if estado.get("choices"):
        print(f"  opciones:     {' | '.join(estado['choices'])}")


def main() -> int:
    print("=== Estado actual ===")
    _imprimir(metricas.estado_fan())
    print()

    argv = sys.argv[1:]
    if not argv:
        print("Para cambiarlo:  python3 test_fan.py [silencioso|normal|overboost]")
        return 0

    nombre = argv[0].lower()
    mapeo = {
        "silencioso": 2,
        "quiet": 2,
        "normal": 0,
        "balanced": 0,
        "overboost": 1,
        "performance": 1,
    }
    if nombre not in mapeo:
        print(f"✗ Modo desconocido: {nombre}")
        return 2

    modo = mapeo[nombre]
    print(f"=== Cambiando a {nombre} (modo lógico {modo}) ===")
    ok, msg = metricas.cambiar_fan(modo)
    print(f"  resultado: {'OK' if ok else 'FAIL'}")
    print(f"  mensaje:   {msg}")
    time.sleep(0.5)
    print()
    print("=== Estado tras el cambio ===")
    _imprimir(metricas.estado_fan())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
