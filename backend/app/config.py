from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://clippy:clippy@localhost:5434/clippy"
    sync_database_url: str = "postgresql+psycopg2://clippy:clippy@localhost:5434/clippy"
    
    clips_dir: Path = Path.home() / "Videos/clips"
    work_dir: Path = Path.home() / ".local/share/clippy"
    
    gsr_script: Path = Path.home() / ".local/bin/gsr-replay"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
