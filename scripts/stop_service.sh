#!/usr/bin/env bash
set -euo pipefail

systemctl --user stop tradebot.service
systemctl --user --no-pager status tradebot.service || true
