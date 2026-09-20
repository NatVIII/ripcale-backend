"""Tests for system settings (app/config.py)."""
#region: imports
from app.config import Settings
#endregion


def test_expire_past_days_accepts_none():
    assert Settings(expire_past_days=None).expire_past_days is None


def test_expire_future_days_accepts_none():
    assert Settings(expire_past_days=90, expire_future_days=None).expire_future_days is None


def test_archive_grace_hours_default():
    assert Settings(expire_past_days=90, expire_future_days=None).archive_grace_hours == 6


def test_archive_grace_hours_accepts_none():
    assert Settings(archive_grace_hours=None).archive_grace_hours is None


def test_ingest_interval_default():
    assert Settings(display_timezone="America/New_York").ingest_interval_minutes == 60


def test_ingest_interval_accepts_none():
    assert Settings(ingest_interval_minutes=None).ingest_interval_minutes is None


def test_ingest_startup_delay_default():
    assert Settings(display_timezone="America/New_York").ingest_startup_delay_minutes == 3


def test_config_yaml_is_authoritative_over_env(tmp_path):
    from pydantic_settings import SettingsConfigDict

    (tmp_path / "cfg.yaml").write_text("admin_port: 9999\n")
    (tmp_path / "secrets.env").write_text(
        "RIPCALE_ADMIN_PORT=1234\n"
        "RIPCALE_ADMIN_USERNAME=theadmin\n"
        "RIPCALE_ADMIN_PASSWORD_HASH=testhash\n"
    )

    class T(Settings):
        model_config = SettingsConfigDict(
            env_file=str(tmp_path / "secrets.env"),
            yaml_file=str(tmp_path / "cfg.yaml"),
            env_prefix="RIPCALE_",
            extra="ignore",
        )

    s = T()
    assert s.admin_port == 9999            # config.yaml beats .env
    assert s.admin_username == "theadmin"  # auth from .env (not in config.yaml)
    assert s.admin_password_hash == "testhash"
#endregion
