# Build from the repo root: pyinstaller packaging/windows/clippy.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parents[1]

hidden = (
    collect_submodules("uvicorn")  # loops/protocols are picked by name at runtime
    + collect_submodules("backend")  # alembic env.py imports backend.app.models by file
    + collect_submodules("alembic")
    + ["aiosqlite", "sqlalchemy.dialects.sqlite", "sqlalchemy.dialects.sqlite.aiosqlite", "pystray._win32"]
)

a = Analysis(
    [str(ROOT / "backend" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "frontend" / "dist"), "frontend/dist"),
        (str(ROOT / "alembic"), "alembic"),  # run as files by alembic, not imported
        (str(ROOT / "bin"), "bin"),  # ffmpeg.exe, ffprobe.exe, clippy-audio.exe
    ],
    hiddenimports=hidden,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Clippy",
    console=False,
    icon=str(Path(SPECPATH) / "clippy.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Clippy")
