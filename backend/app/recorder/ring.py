"""RAM ring buffer of MPEG-TS packets, cut into chunks that each start at a video keyframe."""
import threading
import time

PKT = 188
VIDEO_TYPES = (0x1B, 0x24, 0x02)  # h264, hevc, mpeg2


def _pid(p: bytes) -> int:
    return ((p[1] & 0x1F) << 8) | p[2]


class Ring:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self.chunks: list[tuple[float, bytearray]] = []  # (arrival time of the keyframe, packets)
        self.pat = self.pmt = None
        self.pmt_pid = self.video_pid = None
        self._tail = b""
        self._lock = threading.Lock()

    def _parse_pat(self, p: bytes):
        t = p[5:]  # 4 header bytes + pointer field; ffmpeg's PAT/PMT never carry an adaptation field
        end = 3 + (((t[1] & 15) << 8) | t[2]) - 4
        for i in range(8, end, 4):
            if (t[i] << 8 | t[i + 1]) != 0:
                self.pmt_pid = ((t[i + 2] & 0x1F) << 8) | t[i + 3]
                return

    def _parse_pmt(self, p: bytes):
        t = p[5:]
        end = 3 + (((t[1] & 15) << 8) | t[2]) - 4
        i = 12 + (((t[10] & 15) << 8) | t[11])
        while i + 5 <= end:
            if t[i] in VIDEO_TYPES:
                self.video_pid = ((t[i + 1] & 0x1F) << 8) | t[i + 2]
                return
            i += 5 + (((t[i + 3] & 15) << 8) | t[i + 4])

    def feed(self, data: bytes, now: float | None = None):
        now = time.monotonic() if now is None else now
        data = self._tail + data
        n = len(data) // PKT * PKT
        self._tail = data[n:]
        with self._lock:
            for i in range(0, n, PKT):
                p = data[i:i + PKT]
                pid, pusi = _pid(p), p[1] & 0x40
                if pid == 0 and pusi:
                    self.pat = p
                    self._parse_pat(p)
                elif pid == self.pmt_pid and pusi:
                    self.pmt = p
                    self._parse_pmt(p)
                elif pid == self.video_pid and (p[3] >> 4) & 2 and p[4] > 0 and p[5] & 0x40:
                    self.chunks.append((now, bytearray()))
                if self.chunks:
                    self.chunks[-1][1].extend(p)
            # keep >= `seconds` of history and always begin on a keyframe
            while len(self.chunks) > 1 and self.chunks[1][0] <= now - self.seconds:
                self.chunks.pop(0)

    def snapshot(self, seconds: float | None = None, now: float | None = None) -> bytes:
        """PAT + PMT + everything from the latest keyframe at least `seconds` old (None = whole buffer)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            start = 0
            if seconds is not None:
                for i, (t, _) in enumerate(self.chunks):
                    if t <= now - seconds:
                        start = i
            if not self.chunks or not self.pat or not self.pmt:
                return b""
            return self.pat + self.pmt + b"".join(bytes(c) for _, c in self.chunks[start:])
