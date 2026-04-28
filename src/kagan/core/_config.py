"""Config-path helper for kagan.core."""

import os
from pathlib import Path


def default_config_path() -> Path:
    kagan_override = os.environ.get("KAGAN_CONFIG_DIR")
    if kagan_override:
        return Path(kagan_override) / "config.toml"
    from platformdirs import user_config_dir

    return Path(user_config_dir("kagan", "kagan")) / "config.toml"
