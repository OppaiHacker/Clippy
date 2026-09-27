import pytest
from pydantic import ValidationError
from backend.app.api import recorder as r

def test_recorder_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "RECORDER_CONF", tmp_path / "recorder.env")
    monkeypatch.setattr(r.shutil, "which", lambda _: None)
    monkeypatch.setattr(r, "get_recorder_status", lambda: {"running": False})
    cfg = r.RecorderConfig(fps=144, buffer=120, binds={**r.RecorderConfig().binds, "save_60": "SUPER + SHIFT + S"})
    r.put_recorder_config(cfg)
    assert r.read_config() == cfg
    with pytest.raises(ValidationError):  # would break out of the quotes in the sourced shell file
        r.RecorderConfig(binds={**r.RecorderConfig().binds, "toggle": 'ALT"; rm -rf ~; "'})
