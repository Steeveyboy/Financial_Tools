"""Configuration loader.

Reads application.yaml for structural config and pulls credentials
from environment variables.
"""

import os
from pathlib import Path
from typing import Any

import yaml

_CONFIG_CACHE: dict | None = None
_CONFIG_DIR = Path(__file__).resolve().parent


def _load_yaml(path: Path | None = None) -> dict:
    """Load and cache the application.yaml file."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    if path is None:
        path = _CONFIG_DIR / "application.yaml"

    with open(path, "r") as f:
        _CONFIG_CACHE = yaml.safe_load(f)

    return _CONFIG_CACHE


def get(key: str, default: Any = None) -> Any:
    """Retrieve a dot-separated key from the loaded config.

    Example:
        get("database.name")          -> "financial_datawarehouse"
        get("fetcher.rate_limit_delay") -> 0.2
    """
    cfg = _load_yaml()
    parts = key.split(".")
    node: Any = cfg
    for part in parts:
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return default
        if node is None:
            return default
    return node


def get_connection_string() -> str:
    """Return the PostgreSQL connection string from the environment.

    Checks POSTGRES_CONNECTION_STRING first, then DATABASE_URL.
    Raises RuntimeError if neither is set.
    """
    conn = os.environ.get("POSTGRES_CONNECTION_STRING") or os.environ.get(
        "DATABASE_URL"
    )
    if not conn:
        raise RuntimeError(
            "Set the POSTGRES_CONNECTION_STRING or DATABASE_URL environment variable "
            "to a valid PostgreSQL connection URI "
            "(e.g. postgresql://user:pass@host:5432/dbname)."
        )
    return conn


def reload() -> dict:
    """Force-reload the configuration from disk."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
    return _load_yaml()
