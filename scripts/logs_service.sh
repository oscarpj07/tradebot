#!/usr/bin/env bash
set -euo pipefail

journalctl --user -u tradebot.service -f
