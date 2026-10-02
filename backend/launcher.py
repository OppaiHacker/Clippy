"""Entry point of the Windows exe (also runs from source): server + tray icon."""
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

PORT = 8723


def _hide_console_windows():
    # ffmpeg & co. would flash a console each time from a windowed app
    if sys.platform != "win32":
        return
    orig = subprocess.Popen.__init__

    def init(self, *a, **kw):
        kw["creationflags"] = kw.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        orig(self, *a, **kw)

    subprocess.Popen.__init__ = init


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.read()


def _is_clippy(port: int) -> bool:
    try:
        _get(f"http://127.0.0.1:{port}/api/clips")
        return True
    except Exception:
        return False


def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def icon_image(size: int = 64):
    from PIL import Image, ImageDraw
    k = 4  # supersample for smooth edges
    s = size * k
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 9 // 32, fill="#1a1930")
    d.polygon([(s * .38, s * .28), (s * .76, s * .5), (s * .38, s * .72)], fill="#8470ff")
    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    from backend.app.config import resource_dir, settings
    os.environ["PATH"] = str(resource_dir / "bin") + os.pathsep + os.environ.get("PATH", "")
    _hide_console_windows()

    settings.work_dir.mkdir(parents=True, exist_ok=True)
    log = open(settings.work_dir / "clippy.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None or sys.stderr is None:  # windowed exe has no std streams
        sys.stdout = sys.stderr = log
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(log)],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    smoke = "--smoke" in sys.argv
    if not _free(PORT) and not smoke:
        if _is_clippy(PORT):
            webbrowser.open(f"http://127.0.0.1:{PORT}")
            return 0
    port = PORT if _free(PORT) else 0
    if port == 0:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}"

    import uvicorn
    from backend.app.main import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    thread = threading.Thread(target=server.run, name="uvicorn")
    thread.start()
    while not server.started and thread.is_alive():
        time.sleep(0.1)
    if not server.started:
        return 1

    def stop():
        server.should_exit = True
        thread.join(timeout=30)

    if smoke:
        try:
            _get(f"{url}/api/clips")
            assert b"<" in _get(f"{url}/")
            print("smoke ok")
            return 0
        except Exception as e:
            print(f"smoke failed: {e}")
            return 1
        finally:
            stop()

    if "--background" not in sys.argv:  # autostart at login: tray only, no browser tab every boot
        webbrowser.open(url)
    try:
        import pystray
    except ImportError:
        thread.join()
        return 0
    open_ = pystray.MenuItem("Open Clippy", lambda: webbrowser.open(url), default=True)
    quit_ = pystray.MenuItem("Quit", lambda icon: (stop(), icon.stop()))
    icon = pystray.Icon("Clippy", icon_image(), "Clippy", pystray.Menu(open_, quit_))
    threading.Thread(target=lambda: (thread.join(), icon.stop()), daemon=True).start()
    icon.run()
    stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
