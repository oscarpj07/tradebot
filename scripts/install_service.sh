#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="tradebot.service"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"

mkdir -p "${USER_SYSTEMD_DIR}"
cp "${ROOT_DIR}/systemd/${SERVICE_NAME}" "${USER_SYSTEMD_DIR}/${SERVICE_NAME}"

systemctl --user daemon-reload
systemctl --user enable "${SERVICE_NAME}"
systemctl --user restart "${SERVICE_NAME}"

if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "${USER}" || true
fi

systemctl --user --no-pager status "${SERVICE_NAME}"
