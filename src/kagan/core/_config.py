"""Bootstrap TOML config for kagan.core — only settings needed before the DB exists."""

import os
from dataclasses import dataclass
from pathlib import Path

import tomlkit
from loguru import logger


@dataclass
class KaganBootstrapConfig:
    db_path: str | None = None
    log_level: str = "INFO"


def default_config_path() -> Path:
    kagan_override = os.environ.get("KAGAN_CONFIG_DIR")
    if kagan_override:
        return Path(kagan_override) / "config.toml"
    from platformdirs import user_config_dir

    return Path(user_config_dir("kagan", "kagan")) / "config.toml"


def load_config(config_path: Path | None = None) -> KaganBootstrapConfig:
    path = config_path if config_path is not None else default_config_path()
    logger.debug("Loading config from {}", path)
    if not path.exists():
        logger.debug("Config file not found, using defaults")
        return KaganBootstrapConfig()

    text = path.read_text(encoding="utf-8")
    doc = tomlkit.loads(text)

    db_path_raw = doc.get("db_path")
    db_path: str | None = str(db_path_raw) if db_path_raw is not None else None

    log_level_raw = doc.get("log_level")
    log_level: str = str(log_level_raw) if log_level_raw is not None else "INFO"

    return KaganBootstrapConfig(db_path=db_path, log_level=log_level)


def save_config(cfg: KaganBootstrapConfig, config_path: Path | None = None) -> None:
    path = config_path if config_path is not None else default_config_path()
    logger.debug("Saving config to {}", path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = tomlkit.document()
    if cfg.db_path is not None:
        doc.add("db_path", cfg.db_path)
    doc.add("log_level", cfg.log_level)

    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
