"""One ffmpeg encodes screen + audio to MPEG-TS on stdout; we keep the last N seconds in RAM
and remux a slice to mp4 on save. Nothing is ever buffered on disk."""
import collections
import functools
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from backend.app.config import settings
from .ring import Ring

logger = logging.getLogger(__name__)
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ddagrab yields d3d11 frames that stay on the GPU. nvenc and amf take d3d11 frames as they are,
# qsv needs hwmap into its own device, the software fallback has to download them.
# `-bf 0` (or the encoder default) keeps the TS cuttable at any keyframe.
ENCODERS = {
    "h264_nvenc": ("", "-preset p5 -tune hq -rc vbr -cq 20 -b:v 0 -maxrate 80M -bf 0"),
    "h264_amf": ("", "-quality quality -rc vbr_peak -b:v 40M -maxrate 80M -bf 0"),
    "h264_qsv": ("hwmap=derive_device=qsv,format=qsv", "-preset slow -global_quality 20 -bf 0"),
    "libx264": ("hwdownload,format=bgra,format=yuv420p", "-preset veryfast -crf 20 -bf 0"),
}


@functools.lru_cache(maxsize=None)
def pick_encoder(monitor: int) -> str:
    """First encoder that really takes this monitor's ddagrab frames. Listed in ffmpeg != usable GPU,
    and on hybrid laptops the GPU that drives the screen is often not the one with nvenc."""
    for enc, (vf, _) in list(ENCODERS.items())[:-1]:
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"ddagrab=output_idx={monitor}",
               "-frames:v", "1", *(["-vf", vf] if vf else []), "-c:v", enc, "-f", "null", "-"]
        try:
            if subprocess.run(cmd, capture_output=True, timeout=10, creationflags=NO_WINDOW).returncode == 0:
                return enc
        except subprocess.TimeoutExpired:
            pass
    logger.warning("no hardware h264 encoder works, falling back to libx264 (high CPU use)")
    return "libx264"


def build_cmd(fps: int, video_input: list[str], audio_inputs: list[list[str]], encoder: str, hw: bool) -> list[str]:
    vf, args = ENCODERS[encoder]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", *video_input]
    for a in audio_inputs:
        cmd += a
    cmd += ["-map", "0:v"] + [x for i in range(len(audio_inputs)) for x in ("-map", f"{i + 1}:a")]
    cmd += ["-c:v", encoder, *args.split(), "-g", str(fps)]
    if hw and vf:
        cmd += ["-vf", vf]
    if encoder == "libx264" and not hw:
        cmd += ["-tune", "zerolatency"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-f", "mpegts", "-flush_packets", "1", "-mpegts_flags", "+resend_headers", "pipe:1"]
    return cmd


def foreground_window() -> tuple[str | None, str | None]:
    """(exe name without .exe, window title) of the focused window."""
    if sys.platform != "win32":
        return None, None
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    u32.GetForegroundWindow.restype = wintypes.HWND
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return None, None
    title = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(hwnd, title, 512)
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = None
    h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        buf, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            exe = Path(buf.value).stem
        k32.CloseHandle(h)
    return exe, title.value or None


def _pipe_ready(name: str) -> bool:
    import ctypes
    return bool(ctypes.WinDLL("kernel32").WaitNamedPipeW(name, 100))  # unlike open(), does not eat the instance


class Engine:
    RESTART_AFTER = 10  # seconds an ffmpeg must have run before its exit counts as a hiccup worth a restart

    def __init__(self, inputs=None):
        # inputs = (video_input, audio_inputs, titles): lavfi sources for tests instead of ddagrab + pipes
        self._inputs = inputs
        self._lock = threading.Lock()
        self._closed = False  # app is shutting down: a late start (autostart thread, hotkey) must not spawn ffmpeg
        self._cfg = None  # set while the buffer should be on: the watchdog restarts ffmpeg with it
        self.proc: subprocess.Popen | None = None
        self.helpers: list[subprocess.Popen] = []
        self.ring: Ring | None = None
        self.titles: list[str] = []
        self.fps = self.buffer = 0
        self.encoder = ""
        self.error = ""
        self.warning = ""
        self._stderr: collections.deque[str] = collections.deque(maxlen=15)

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def status(self) -> str:
        if self.running:
            return f"running (buffer {self.buffer}s, {self.fps}fps -> {self.encoder})" + (f" [{self.warning}]" if self.warning else "")
        err = self.error or (" | ".join(self._stderr) if self.proc else "")
        return "stopped" + (f": {err}" if err else "")

    def _real_inputs(self, cfg):
        helper = shutil.which("clippy-audio")
        if not helper:
            self.warning = "clippy-audio not found, recording without audio"
            return ["-f", "lavfi", "-i", f"ddagrab=output_idx={cfg.monitor}:framerate={cfg.fps}"], [], []
        # Process loopback can only EXCLUDE one process tree, so the browser is also on track 1.
        tracks = [(f"All applications except: {cfg.voice_app}", ["--exclude", cfg.voice_app]),
                  (f"Applications: {cfg.voice_app}", ["--include", cfg.voice_app]),
                  (f"Applications: {cfg.browser_app}", ["--include", cfg.browser_app]),
                  ("Devices: default_input", ["--mic"])]
        run, audio = uuid.uuid4().hex[:8], []
        for n, (_, flags) in enumerate(tracks):
            name = f"clippy-{run}-{n}"
            self.helpers.append(subprocess.Popen([helper, "capture", "--pipe", name, *flags], creationflags=NO_WINDOW,
                                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            for _ in range(100):  # WaitNamedPipe returns at once while the pipe does not exist yet
                if _pipe_ready(rf"\\.\pipe\{name}"):
                    break
                if self.helpers[-1].poll() is not None:
                    raise RuntimeError(f"clippy-audio exited for track {n + 1}")
                time.sleep(0.1)
            else:
                raise RuntimeError(f"audio pipe {name} never appeared")
            audio.append(["-f", "f32le", "-ar", "48000", "-ac", "2", "-thread_queue_size", "4096", "-i", rf"\\.\pipe\{name}"])
        return ["-f", "lavfi", "-i", f"ddagrab=output_idx={cfg.monitor}:framerate={cfg.fps}"], audio, [t for t, _ in tracks]

    def start(self, cfg) -> str:
        with self._lock:
            return self._start(cfg)

    def _start(self, cfg) -> str:
        if self._closed:
            return self.status()
        if self.running:
            return self.status()
        self._kill()
        self.error = self.warning = ""
        self._stderr.clear()
        try:
            if self._inputs:
                video, audio, self.titles = self._inputs
                self.encoder = "libx264"
            else:
                self.encoder = pick_encoder(cfg.monitor)
                video, audio, self.titles = self._real_inputs(cfg)
            self.fps, self.buffer, self.ring, self._cfg = cfg.fps, cfg.buffer, Ring(cfg.buffer), cfg
            self.proc = subprocess.Popen(build_cmd(cfg.fps, video, audio, self.encoder, hw=not self._inputs),
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         creationflags=NO_WINDOW)
        except Exception as e:
            logger.error("recorder start failed: %s", e)
            self.error = str(e)
            self._kill()
            return self.status()
        threading.Thread(target=self._pump, args=(self.proc, self.ring), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(self.proc,), daemon=True).start()
        return self.status()

    def _pump(self, proc, ring):
        started = time.monotonic()
        while chunk := proc.stdout.read1(188 * 256):
            ring.feed(chunk)
        proc.wait()
        # ffmpeg quit on its own: a game switched resolution, a UAC prompt took the desktop, a driver reset.
        # Start a fresh one (the old buffer is lost); one that dies right away is a real error and stays stopped.
        if time.monotonic() - started < self.RESTART_AFTER:
            return
        time.sleep(1)
        with self._lock:
            if self.proc is proc and self._cfg:
                logger.warning("ffmpeg exited (%s), restarting the replay buffer", " | ".join(self._stderr))
                self._start(self._cfg)

    def _drain_stderr(self, proc):
        for line in proc.stderr:
            self._stderr.append(line.decode(errors="replace").strip())

    def _kill(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
                self.proc.wait(3)
            except Exception:
                self.proc.kill()
        for h in self.helpers:  # they exit on their own once ffmpeg disconnects; this covers a failed start
            if h.poll() is None:
                h.terminate()
        self.helpers = []

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self.stop()

    def stop(self) -> str:
        with self._lock:
            self._cfg = None
            self._kill()
            self.proc = None
            self.ring = None
            return self.status()

    def save(self, seconds: int | None, clips_dir: Path | None = None) -> Path:
        """Write the last `seconds` (None = whole buffer) to <clips_dir>/Replay_<time>.mp4 plus its sidecar."""
        if not self.running or not self.ring:
            raise RuntimeError("replay buffer is off")
        data = self.ring.snapshot(seconds)
        if not data:
            raise RuntimeError("replay buffer is still empty")
        clips_dir = clips_dir or settings.clips_dir
        clips_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now().astimezone()
        final = clips_dir / f"Replay_{now:%Y-%m-%d_%H-%M-%S}.mp4"
        n = 1
        while final.exists():  # two saves in one second must not overwrite each other
            n += 1
            final = clips_dir / f"Replay_{now:%Y-%m-%d_%H-%M-%S}_{n}.mp4"
        tmp = clips_dir / f".{final.name}.part"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "mpegts", "-i", "pipe:0",
               "-map", "0:v", "-map", "0:a?", "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart"]
        for i, title in enumerate(self.titles):
            cmd += [f"-metadata:s:a:{i}", f"title={title}"]
        r = subprocess.run(cmd + ["-f", "mp4", str(tmp)], input=data, capture_output=True, creationflags=NO_WINDOW)
        if r.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(r.stderr.decode(errors="replace").strip() or "ffmpeg remux failed")
        # sidecar first, clip last: the watcher ingests the clip once, with its sidecar already there
        game, title = foreground_window()
        final.with_suffix(".json").write_text(json.dumps({
            "file": final.name, "type": "replay", "saved_at": now.isoformat(timespec="seconds"),
            "game": game, "window_title": title, "monitor": None, "audio_apps": self._audio_apps()}))
        os.replace(tmp, final)
        return final

    @staticmethod
    def _audio_apps() -> list[str]:
        helper = shutil.which("clippy-audio")
        if not helper:
            return []
        try:
            r = subprocess.run([helper, "list"], capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW)
            return [a["name"] for a in json.loads(r.stdout)]
        except Exception:
            return []


engine = Engine()
