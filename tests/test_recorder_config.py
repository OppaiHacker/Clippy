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

def test_windows_fields_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "RECORDER_CONF", tmp_path / "recorder.env")
    assert r.read_config().voice_app == "Discord.exe"
    (tmp_path / "recorder.env").write_text("FPS=60\nVOICE_APP=Vesktop.exe\nMONITOR=1\nAUTOSTART=0\n")
    cfg = r.read_config()
    assert (cfg.voice_app, cfg.monitor, cfg.autostart) == ("Vesktop.exe", 1, False)
    with pytest.raises(ValidationError):
        r.RecorderConfig(browser_app="x.exe --evil")
