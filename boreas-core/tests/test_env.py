"""The .env loader exists because nothing else in the service reads
boreas-core/.env -- without it, configured credentials are invisible and the
satellite subsystem reports itself unconfigured while the file sits populated.
"""

import os

from boreas_core.env import load_env_file


def test_loads_keys_into_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "CDSE_CLIENT_ID=abc123",
                'CDSE_CLIENT_SECRET="quoted-secret"',
                "export EXPORTED_KEY=exported-value",
                "EMPTY_VALUE=",
                "NOT_AN_ASSIGNMENT",
            ]
        ),
        encoding="utf-8",
    )
    for key in ("CDSE_CLIENT_ID", "CDSE_CLIENT_SECRET", "EXPORTED_KEY", "EMPTY_VALUE"):
        monkeypatch.delenv(key, raising=False)

    applied = load_env_file(env)

    assert os.environ["CDSE_CLIENT_ID"] == "abc123"
    assert os.environ["CDSE_CLIENT_SECRET"] == "quoted-secret"
    assert os.environ["EXPORTED_KEY"] == "exported-value"
    # Blank values and non-assignments are skipped rather than setting empties
    # that would read as "configured".
    assert "EMPTY_VALUE" not in applied
    assert "NOT_AN_ASSIGNMENT" not in applied


def test_real_environment_wins_over_the_file(tmp_path, monkeypatch):
    """Container/CI configuration must not be clobbered by a stale local file."""
    env = tmp_path / ".env"
    env.write_text("CDSE_CLIENT_ID=from-file", encoding="utf-8")
    monkeypatch.setenv("CDSE_CLIENT_ID", "from-environment")

    load_env_file(env)

    assert os.environ["CDSE_CLIENT_ID"] == "from-environment"


def test_override_is_opt_in(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("CDSE_CLIENT_ID=from-file", encoding="utf-8")
    monkeypatch.setenv("CDSE_CLIENT_ID", "from-environment")

    load_env_file(env, override=True)

    assert os.environ["CDSE_CLIENT_ID"] == "from-file"


def test_missing_file_is_not_an_error(tmp_path):
    """Running without a .env is a supported configuration."""
    assert load_env_file(tmp_path / "does-not-exist") == {}
