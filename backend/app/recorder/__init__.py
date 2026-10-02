"""Native Windows replay recorder (ffmpeg + RAM ring buffer). startup/shutdown are no-ops elsewhere."""
import sys
import threading

from . import hotkeys
from .engine import engine

WIN = sys.platform == "win32"


def _on_action(action: str):
    from ..api.recorder import read_config
    if action == "toggle":
        engine.stop() if engine.running else engine.start(read_config())
    else:
        try:
            engine.save(None if action == "save_full" else int(action.removeprefix("save_")))
        except RuntimeError:
            pass  # buffer off or empty


def rebind(cfg) -> None:
    hotkeys.register(cfg.binds, _on_action)


def startup() -> None:
    if not WIN:
        return
    from ..api.recorder import read_config
    cfg = read_config()
    rebind(cfg)
    if cfg.autostart:  # off-thread: waiting for the audio pipes must not delay the API
        threading.Thread(target=engine.start, args=(cfg,), daemon=True).start()


def shutdown() -> None:
    if WIN:
        hotkeys.stop()
        engine.close()
