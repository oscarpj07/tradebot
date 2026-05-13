import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

STATE_FILE = Path(__file__).with_name("state.json")


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open() as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load state file {STATE_FILE}: {e}")
        return {}


def save_state_section(section, value):
    state = load_state()
    state[section] = value

    tmp_file = STATE_FILE.with_suffix(".json.tmp")
    with tmp_file.open("w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    tmp_file.replace(STATE_FILE)
