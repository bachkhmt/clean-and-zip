"""Persistent desktop preferences for CleanZip."""

import json
import os


CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".cleanzip_config.json")


def default_config():
    return {
        "history": [],
        "theme": "Dark",
        "auto_open": True,
        "skip_media": True,
        "auto_scan": True,
        "project_excludes": {},
    }


def load_config():
    """Load known, well-typed options; preserve malformed files as a .bak."""
    result = default_config()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            for key, value in data.items():
                if key not in result or isinstance(value, type(result[key])):
                    result[key] = value
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        try:
            os.replace(CONFIG_FILE, CONFIG_FILE + ".bak")
        except OSError:
            pass
    return result


def save_config(cfg):
    """Write configuration atomically so interruptions cannot truncate the file."""
    tmp_path = CONFIG_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(cfg, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, CONFIG_FILE)
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
