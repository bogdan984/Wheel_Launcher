#!/usr/bin/env bash
# Сборка Windows-версии на Linux: Docker + Wine. tobix/pywine (Windows-Python 3.13) — PyInstaller,
# amake/innosetup — установщик.
# Результат: dist/Wheel Launcher/ (программа) и dist/Wheel_Launcher_Setup_<версия>.exe (установщик).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(grep -oP '^APP_VERSION = "\K[^"]+' "$ROOT/wheel_launcher.py")"

docker run --rm -v "$ROOT":/src -w /src tobix/pywine:3.13 bash -c "
set -e
export WINEDEBUG=-all
rm -rf dist build/work
wine python -m pip install -q --disable-pip-version-check pyinstaller==6.16.0 pygame==2.6.1 vgamepad==0.1.0
wine python -m PyInstaller --noconfirm --clean --windowed --onedir --noupx \
  --name 'Wheel Launcher' --icon 'Z:\\src\\wheel_launcher.ico' --add-data 'Z:\\src\\wheel_launcher.ico;.' \
  --collect-all vgamepad --exclude-module pytest \
  --distpath dist --workpath build/work --specpath build/work \
  wheel_launcher.py
chown -R $(id -u):$(id -g) dist build/work
"
chmod 777 "$ROOT/dist"          # в amake/innosetup другой пользователь
docker run --rm -e LANG=C.UTF-8 -e LC_ALL=C.UTF-8 -v "$ROOT":/work -w /work/build amake/innosetup /Q /DAppVersion=$VERSION installer.iss
chmod 755 "$ROOT/dist"
ls -la "$ROOT/dist"
