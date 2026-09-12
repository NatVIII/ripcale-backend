"""Application configuration.

`settings = Settings()` is instantiated once at import time and is read by
nearly every other gatherer (db, registry, routers, security, ...). Values are
loaded with this precedence:

    init kwargs > environment / `.env` > `config.yaml` > defaults

API keys and secrets belong in `.env`; system settings in `config.yaml`; the
mutable intake data (sources, gatherers, category symlinks) in `intake.yaml`
(see `app/intake.py`).
"""
#region: imports
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
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
    # Intake settings file (sources, gatherers, category symlinks) — separate
    # from this system config so the program can edit it (see app/intake.py).
    intake_file: str = "intake.yaml"

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

    # Bearer token for the /api/v1/* admin API. If empty, the API is disabled.
    api_token: str = ""

    # Admin login (bootstrap only — seeds the initial `User` row). `admin_password_hash`
    # is an argon2id hash (generate with `python -m app.auth hash-password`).
    admin_username: str = "admin"
    admin_password_hash: str = ""

    # Optional pepper: a secret keyed into every password before hashing
    # (defense-in-depth if the DB alone leaks). Empty = disabled. Generate with
    # `python -m app.auth gen-pepper`. Changing it invalidates existing hashes.
    pepper: str = ""

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
