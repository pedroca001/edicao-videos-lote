#!/bin/bash
set -euo pipefail
editor_source="$(cd -- "$(dirname -- "$0")" && pwd -P)"
editor_root="${EDITOR_INSTALL_ROOT:-$HOME/Library/Application Support/EditorVideosBassi}"
editor_bootstrap="$(mktemp -d -t editor_installer)"
trap 'rm -rf "$editor_bootstrap"' EXIT
trap 'printf "\nA instalacao parou. Copie o erro mostrado acima para suporte.\n"; if [[ -t 0 ]]; then read -r -p "Pressione Enter para fechar."; fi' ERR
if [[ "$(uname -s)" != Darwin ]]; then echo "Este instalador e para macOS."; exit 1; fi
editor_macos_major="$(sw_vers -productVersion | cut -d. -f1)"
if (( editor_macos_major < 14 )); then
  echo 'Atualize para macOS Sonoma 14 ou mais novo antes de instalar este pacote.'
  exit 1
fi
mkdir -p "$editor_root/tools"
export UV_PYTHON_INSTALL_DIR="$editor_root/python"
export UV_NO_MODIFY_PATH=1
export UV_PYTHON_BIN_DIR="$editor_root/tools"
echo '1/4 Preparando Python e instalador...'
if [[ ! -x "$editor_root/tools/uv" ]]; then
  curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error https://astral.sh/uv/0.12.13/install.sh -o "$editor_bootstrap/uv.sh"
  UV_INSTALL_DIR="$editor_root/tools" sh "$editor_bootstrap/uv.sh"
fi
"$editor_root/tools/uv" python install 3.12
if [[ ! -x "$editor_root/venv/bin/python" ]]; then
  "$editor_root/tools/uv" venv --python 3.12 "$editor_root/venv"
fi
echo '2/4 Instalando dependencias locais...'
editor_arch="$("$editor_root/venv/bin/python" -c 'import platform; print(platform.machine())')"
if [[ "$editor_arch" != arm64 ]]; then
  echo 'Este pacote foi preparado para Macs Apple Silicon (M1 ou mais novo). Abra um Terminal nativo, sem Rosetta.'
  exit 1
fi
"$editor_root/tools/uv" pip install --python "$editor_root/venv/bin/python" --only-binary :all: -r "$editor_source/requirements_apple.txt"
echo '3/4 Copiando aplicativo e baixando o modelo de transcricao...'
PYTHONDONTWRITEBYTECODE=1 "$editor_root/venv/bin/python" -B "$editor_source/install_runtime.py" --root "$editor_root"
echo '4/4 Instalacao concluida. Abra iniciar_editor.command nesta pasta.'
if [[ -t 0 && "${EDITOR_NONINTERACTIVE:-0}" != 1 ]]; then read -r -p 'Pressione Enter para fechar.'; fi
