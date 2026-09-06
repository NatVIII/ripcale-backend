"""Application configuration.

`settings = Settings()` is instantiated once at import time and is read by
nearly every other gatherer (db, registry, routers, security, ...). Values are
loaded with this precedence:

    init kwargs > environment / `.env` > `config.yaml` > defaults

API keys and secrets belong in `.env`; everything else in `config.yaml`.
"""
#region: imports
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from app.schema import GathererConfig, SourceConfig
#endregion


#region: settings
class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        yaml_file="config.yaml",
        env_prefix="RIPCALE_",
        extra="ignore",
    )

    # -- server -----------------------------------------------------------
    # Public (read-only) listener.
    public_host: str = "0.0.0.0"
    public_port: int = 8081
    # Admin (interactive/debug) listener — loopback-only by default.
    admin_host: str = "127.0.0.1"
    admin_port: int = 8082

    # -- storage ----------------------------------------------------------
    data_dir: str = "data"
    database_url: str | None = None

    # -- logging ----------------------------------------------------------
    # Path to the rotating log file. Relative paths are resolved against
    # `data_dir`; absolute paths are used as-is. Empty = `{data_dir}/ripcale.log`.
    log_file: str | None = None
    # RotatingFileHandler caps: rotate once the file reaches `log_max_bytes`,
    # keeping `log_backup_count` rotated backups (disk capped at
    # ~max_bytes * (backup_count + 1)).
    log_max_bytes: int = 1_000_000
    log_backup_count: int = 3

    # -- http -------------------------------------------------------------
    cors_origins: str = "*"

    # -- debug / admin access ---------------------------------------------
    # Comma-separated IPv4 CIDRs allowed to hit /debug* endpoints.
    # Loopback is always allowed; empty string = localhost only.
    debug_allowed_cidrs: str = ""
    # Optional fixed CSRF token for the pipeline playground. If empty, an
    # ephemeral token is generated at startup.
    debug_token: str = ""

    # -- gatherers / sources ---------------------------------------------
    # Per-gatherer defaults, extensible (e.g. `priority`). See GathererConfig.
    gatherers: dict[str, GathererConfig] = {}
    sources: list[SourceConfig] = []

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        """Insert the YAML source below env/.env but above defaults."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    @property
    def resolved_database_url(self) -> str:
        """Return the DB URL, defaulting to a SQLite file under `data_dir`."""
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir}/ripcale.db"


settings = Settings()
#endregion
