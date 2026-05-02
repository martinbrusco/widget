#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d vendor/PyQt6 ]] || [[ ! -d vendor/pyqtgraph ]] || [[ ! -f vendor/psutil/__init__.py ]] || [[ ! -f vendor/yt_dlp/__init__.py ]] || [[ ! -f vendor/deep_translator/__init__.py ]]; then
  echo "Instalando dependencias en ./vendor …"
  pip3 install --target ./vendor -r requirements.txt
fi
export PYTHONPATH="${PWD}/vendor:${PYTHONPATH:-}"
exec python3 widget.py
