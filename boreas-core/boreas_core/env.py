"""Loads `boreas-core/.env` into the process environment.

Without this, every credential in that file is invisible to the running
service: nothing else in the codebase reads it, `uvicorn` does not read it,
and `start.sh` does not export it. The satellite subsystem would then report
"not configured" even when real CDSE credentials are sitting in the file --
the operator's configuration silently ignored.

Deliberately dependency-free rather than pulling in python-dotenv: the format
BOREAS actually uses is a handful of `KEY=value` lines, and parsing that does
not justify another package.

Real environment variables always win over the file, so container/CI
configuration is never clobbered by a stale local .env.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env_file(path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Parses a .env file and applies it to os.environ.

    Returns the keys that were applied, so callers (and tests) can see what
    actually took effect. Missing file is not an error -- running without one
    is a supported configuration, it just means the credential-gated features
    report themselves as unconfigured.
    """
    env_path = path or ENV_PATH
    applied: dict[str, str] = {}

    if not env_path.is_file():
        return applied

    try:
        raw = env_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read %s: %s", env_path, exc)
        return applied

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # `export KEY=value` is common in hand-written env files.
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or not value:
            continue
        if override or not os.environ.get(key):
            os.environ[key] = value
            applied[key] = value

    return applied
