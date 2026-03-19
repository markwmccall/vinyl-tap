import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR: Path = Path.home() / ".local" / "share" / "vinyltap"
CONFIG_PATH: str = str(DATA_DIR / "config.json")
TAGS_PATH: str = str(DATA_DIR / "tags.json")

_VERSION_FILE = PROJECT_ROOT / "VERSION"
VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "0.0.0"


def set_data_dir(path) -> None:
    """Set the data directory and update derived paths. Creates the directory."""
    global DATA_DIR, CONFIG_PATH, TAGS_PATH
    DATA_DIR = Path(path).expanduser().resolve()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH = str(DATA_DIR / "config.json")
    TAGS_PATH = str(DATA_DIR / "tags.json")


def _load_config():
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(
            f"Config file not found: {CONFIG_PATH}. "
            "Visit /settings to configure the device."
        )
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Config file is not valid JSON: {e}")
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
