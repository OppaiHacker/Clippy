import os
import sys
from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WINDOWS = sys.platform == "win32"
DEFAULT_WORK_DIR = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Clippy"
                    if WINDOWS else Path.home() / ".local/share/clippy")

FROZEN = getattr(sys, "frozen", False)
# PyInstaller unpacks data files (frontend dist, alembic, bin) under _MEIPASS
resource_dir = Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    # Linux: Postgres from docker compose. Windows: no Docker, one SQLite file in work_dir.
    # Empty = the platform default, filled in below once work_dir is known.
    database_url: str = "" if WINDOWS else "postgresql+asyncpg://clippy:clippy@localhost:5434/clippy"
    sync_database_url: str = "" if WINDOWS else "postgresql+psycopg2://clippy:clippy@localhost:5434/clippy"
    
    clips_dir: Path = Path.home() / ("Videos/Clippy" if WINDOWS else "Videos/clips")
    work_dir: Path = DEFAULT_WORK_DIR
    
    gsr_script: Path = Path.home() / ".local/bin/gsr-replay"
    
    model_config = SettingsConfigDict(env_file=DEFAULT_WORK_DIR / ".env" if FROZEN else ".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def default_sqlite(self):
        db = self.work_dir / "clippy.db"
        if not self.database_url or not self.sync_database_url:
            self.work_dir.mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{db.as_posix()}"
        if not self.sync_database_url:
            self.sync_database_url = f"sqlite:///{db.as_posix()}"
        return self

    @property
    def audio_dir(self) -> Path:
        p = self.work_dir / "audio"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def thumbs_dir(self) -> Path:
        p = self.work_dir / "thumbs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def waveforms_dir(self) -> Path:
        p = self.work_dir / "waveforms"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def imports_dir(self) -> Path:
        p = self.work_dir / "imports"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def exports_dir(self) -> Path:
        p = self.work_dir / "exports"
        p.mkdir(parents=True, exist_ok=True)
        return p

settings = Settings()
