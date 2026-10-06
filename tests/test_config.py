import json

import config


def test_malformed_config_is_preserved_as_backup(tmp_path, monkeypatch):
    path = tmp_path / ".cleanzip_config.json"
    path.write_text('{"history": [', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", str(path))

    loaded = config.load_config()

    assert loaded["auto_scan"] is True
    assert not path.exists()
    assert (tmp_path / ".cleanzip_config.json.bak").read_text(encoding="utf-8") == '{"history": ['


def test_config_save_is_atomic_and_loads_known_options(tmp_path, monkeypatch):
    path = tmp_path / ".cleanzip_config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", str(path))
    payload = config.default_config()
    payload["auto_scan"] = False
    payload["history"] = ["project"]

    config.save_config(payload)

    assert config.load_config()["auto_scan"] is False
    assert config.load_config()["history"] == ["project"]
    assert not (tmp_path / ".cleanzip_config.json.tmp").exists()
