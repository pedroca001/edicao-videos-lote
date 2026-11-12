#!/bin/bash
set -euo pipefail
editor_root="${EDITOR_INSTALL_ROOT:-$HOME/Library/Application Support/EditorVideosBassi}"
if [[ ! -f "$editor_root/config.json" ]]; then
  echo 'Execute instalar_mac.command primeiro.'
  if [[ -t 0 ]]; then read -r -p 'Pressione Enter para fechar.'; fi
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
set +e
"$editor_root/venv/bin/python" -B "$editor_root/app/batch_assistant.py" "$@"
editor_result=$?
if [[ -t 0 ]]; then read -r -p 'Pressione Enter para fechar.'; fi
exit "$editor_result"
