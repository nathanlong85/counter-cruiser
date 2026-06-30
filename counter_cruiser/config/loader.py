"""Load typed configuration from TOML files with env-var overrides."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from counter_cruiser.config.models import ClientSettings, ServerSettings

_CONFIG_ENV_VAR = 'COUNTER_CRUISER_CONFIG'
_DEFAULT_CLIENT = Path('config/client.toml')
_DEFAULT_SERVER = Path('config/server.toml')


def _load_toml(path: Path) -> dict:
    """Read a TOML file; return empty dict if the file does not exist."""
    if not path.exists():
        return {}
    with open(path, 'rb') as fh:
        raw = tomllib.load(fh)
    # Support optional [counter_cruiser] table wrapper
    return raw.get('counter_cruiser', raw)


def _resolve_path(explicit: Path | None, default: Path) -> Path:
    """Resolve config file path: explicit > env var > default."""
    if explicit is not None:
        return explicit
    env = os.environ.get(_CONFIG_ENV_VAR)
    return Path(env) if env else default


def load_client_config(path: Path | None = None) -> ClientSettings:
    """Load and validate :class:`ClientSettings` from a TOML file.

    Resolution order: *path* argument > ``COUNTER_CRUISER_CONFIG`` env var >
    ``config/client.toml``. Missing files fall back to built-in defaults.
    Environment variables (``COUNTER_CRUISER_*``) override file values.
    """
    resolved = _resolve_path(path, _DEFAULT_CLIENT)
    data = _load_toml(resolved)
    return ClientSettings(**data)


def load_server_config(path: Path | None = None) -> ServerSettings:
    """Load and validate :class:`ServerSettings` from a TOML file.

    Same resolution order as :func:`load_client_config`.
    """
    resolved = _resolve_path(path, _DEFAULT_SERVER)
    data = _load_toml(resolved)
    return ServerSettings(**data)
