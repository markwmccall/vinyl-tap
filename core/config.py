import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = str(PROJECT_ROOT / "config.json")
TAGS_PATH = str(PROJECT_ROOT / "data" / "tags.json")

_VERSION_FILE = PROJECT_ROOT / "VERSION"
VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "0.0.0"


def _load_config():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    # In-memory migration: flat "sn" → services.apple.sn (and vice versa)
    if "sn" in config and "services" not in config:
        config.setdefault("services", {}).setdefault("apple", {})
        config["services"]["apple"]["sn"] = config["sn"]
    elif "services" in config and "apple" in config["services"]:
        config.setdefault("sn", config["services"]["apple"].get("sn"))
    required = ["speaker_ip", "sn", "nfc_mode"]
    missing = [k for k in required if k not in config]
    if missing:
        raise RuntimeError(f"Missing required config fields: {', '.join(missing)}")
    return config


def _save_config(config):
    """Persist config dict to CONFIG_PATH."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def _load_tags():
    if not os.path.exists(TAGS_PATH):
        return []
    try:
        with open(TAGS_PATH) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def _save_tags(tags):
    with open(TAGS_PATH, "w") as f:
        json.dump(tags, f, indent=2)
