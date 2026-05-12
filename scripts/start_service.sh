#!/usr/bin/env bash
set -euo pipefail

systemctl --user start tradebot.service
systemctl --user --no-pager status tradebot.service
