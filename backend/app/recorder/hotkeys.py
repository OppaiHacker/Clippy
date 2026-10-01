"""Global hotkeys via RegisterHotKey, with its own message-loop thread (Windows only)."""
import logging
import queue
import sys
import threading

logger = logging.getLogger(__name__)

MODS = {"ALT": 1, "CTRL": 2, "SHIFT": 4, "SUPER": 8}
KEYS = {"SPACE": 0x20, "RETURN": 0x0D, "TAB": 0x09, "ESCAPE": 0x1B, "PRINT": 0x2C, "INSERT": 0x2D,
        "DELETE": 0x2E, "HOME": 0x24, "END": 0x23, "PRIOR": 0x21, "NEXT": 0x22}
MOD_NOREPEAT, WM_HOTKEY, WM_QUIT, WM_APP = 0x4000, 0x0312, 0x0012, 0x8000


def parse_combo(combo: str) -> tuple[int, int] | None:
    """'ALT + SHIFT + F10' -> (modifier mask, virtual key); '' -> None."""
    if not combo.strip():
        return None
    *mods, key = [k.strip().upper() for k in combo.split("+")]
    if any(m not in MODS for m in mods):
        raise ValueError(f"unknown modifier in {combo!r}")
    if key in KEYS:
        vk = KEYS[key]
    elif len(key) > 1 and key[0] == "F" and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    elif len(key) == 1 and key.isalnum():
        vk = ord(key)
    else:
        raise ValueError(f"unknown key in {combo!r}")
    return sum(MODS[m] for m in mods), vk


class _Loop(threading.Thread):
    def __init__(self, on_action):
        super().__init__(daemon=True)
        self.on_action, self.pending, self.ready, self.tid = on_action, queue.Queue(), threading.Event(), 0

    def run(self):
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        self.tid = ctypes.WinDLL("kernel32").GetCurrentThreadId()
        msg = wintypes.MSG()
        u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # creates the thread's message queue
        self.ready.set()
        ids: dict[int, str] = {}
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP:
                for i in ids:
                    u32.UnregisterHotKey(None, i)
                ids = {}
                for action, combo in self.pending.get_nowait().items():
                    try:
                        parsed = parse_combo(combo)
                    except ValueError as e:
                        logger.warning(e)
                        continue
                    if parsed and u32.RegisterHotKey(None, len(ids) + 1, parsed[0] | MOD_NOREPEAT, parsed[1]):
                        ids[len(ids) + 1] = action
                    elif parsed:
                        logger.warning("hotkey %r (%s) is taken by another app", combo, action)
            elif msg.message == WM_HOTKEY and msg.wParam in ids:
                # off the loop thread: a save takes seconds and must not stall other hotkeys
                threading.Thread(target=self.on_action, args=(ids[msg.wParam],), daemon=True).start()
        for i in ids:
            u32.UnregisterHotKey(None, i)


_loop: _Loop | None = None


def register(binds: dict[str, str], on_action) -> None:
    """(Re)register all binds; on_action(action_name) runs when one fires."""
    global _loop
    if sys.platform != "win32":
        return
    import ctypes
    if _loop is None:
        _loop = _Loop(on_action)
        _loop.start()
        _loop.ready.wait(5)
    _loop.pending.put(binds)
    ctypes.WinDLL("user32").PostThreadMessageW(_loop.tid, WM_APP, 0, 0)


def stop() -> None:
    global _loop
    if _loop is None:
        return
    import ctypes
    ctypes.WinDLL("user32").PostThreadMessageW(_loop.tid, WM_QUIT, 0, 0)
    _loop.join(3)
    _loop = None
