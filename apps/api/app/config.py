from __future__ import annotations

import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/joby.db"
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = ""

    # Paths to config files, resolved for local + docker runtime.
    config_dir: str = ""

    # Comma-separated list of allowed CORS origins. Default is local-only.
    # Set to "*" to allow all (not recommended for LAN deployments).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # USCIS H-1B Employer Data Hub CSV. The default points at the FY2024 file; the
    # refresh script falls back to the archived copy if this URL moves. You can
    # override with USCIS_H1B_CSV_URL in .env.
    uscis_h1b_csv_url: str = (
        "https://www.uscis.gov/sites/default/files/document/data/"
        "Employer_Information_FY2024_Q4.csv"
    )

    def cors_origin_list(self) -> List[str]:
        raw = (self.cors_origins or "").strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def resolved_config_dir(self) -> Path:
        if self.config_dir:
            return Path(self.config_dir)
        for candidate in ("/config", "./config", "../../config"):
            p = Path(candidate)
            if p.exists():
                return p.resolve()
        return Path("./config").resolve()


settings = Settings()
