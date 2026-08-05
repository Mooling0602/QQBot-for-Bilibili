"""配置文件版本迁移。

This module is deliberately invoked in a short-lived, writable deployment
container before the main bot starts.  The long-running bot keeps its main
configuration mounts read-only.
"""

import argparse
import logging
import os
import shutil
from pathlib import Path
from typing import Any

import yaml

CONFIG_VERSION = "0.2.0"
_OLD_LIVE_DESCRIPTION = "推送 UP 主开播提醒到本群"
_NEW_LIVE_DESCRIPTION = "推送 UP 主直播事件到本群"

logger = logging.getLogger("qqbot.updater")


class UpdateError(RuntimeError):
    """Configuration migration cannot be completed safely."""


def _config_path() -> Path:
    configured = os.getenv("QQBOT_CONFIG")
    return Path(configured).expanduser() if configured else Path.cwd() / "config.yml"


def _features_path() -> Path:
    configured = os.getenv("QQBOT_FEATURES")
    return Path(configured).expanduser() if configured else Path.cwd() / "features.yml"


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise UpdateError(f"配置文件不存在: {path}")
    try:
        with open(path, encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
    except OSError as error:
        raise UpdateError(f"无法读取配置文件 {path}: {error}") from error
    except yaml.YAMLError as error:
        raise UpdateError(f"配置文件 YAML 无效 {path}: {error}") from error
    if not isinstance(data, dict):
        raise UpdateError(f"配置文件必须是映射: {path}")
    return data


def _write_mapping(path: Path, data: dict[str, Any]) -> None:
    backup = path.with_name(f"{path.name}.bak")
    try:
        if not backup.exists():
            shutil.copy2(path, backup)
        with open(path, "w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
    except OSError as error:
        raise UpdateError(f"无法写入配置文件 {path}: {error}") from error


def migrate(config_path: Path, features_path: Path) -> tuple[bool, bool]:
    """Upgrade the two deployment configuration files to ``CONFIG_VERSION``.

    Returns booleans indicating whether ``config.yml`` and ``features.yml``
    were changed. Existing custom values are retained; only absent fields and
    the known old default description are adjusted.
    """
    config = _load_mapping(config_path)
    features_document = _load_mapping(features_path)
    config_changed = False
    features_changed = False

    if config.get("version") != CONFIG_VERSION:
        config["version"] = CONFIG_VERSION
        config_changed = True
    if "live_monitor" not in config:
        config["live_monitor"] = False
        config_changed = True

    feature_map = features_document.get("features")
    if not isinstance(feature_map, dict):
        feature_map = {}
        features_document["features"] = feature_map
        features_changed = True

    live_alert = feature_map.get("live_alert")
    if not isinstance(live_alert, dict):
        live_alert = {}
        feature_map["live_alert"] = live_alert
        features_changed = True

    defaults: dict[str, Any] = {
        "enable": False,
        "mids": [],
        "prompt": "",
        "add_url": False,
        "notify_on_close": False,
        "prompt_on_close": "",
    }
    for key, value in defaults.items():
        if key not in live_alert:
            live_alert[key] = value
            features_changed = True
    if live_alert.get("description") in (None, _OLD_LIVE_DESCRIPTION):
        live_alert["description"] = _NEW_LIVE_DESCRIPTION
        features_changed = True

    if config_changed:
        _write_mapping(config_path, config)
    if features_changed:
        _write_mapping(features_path, features_document)
    return config_changed, features_changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QQBot 配置版本迁移器")
    parser.add_argument("--config", type=Path, default=_config_path())
    parser.add_argument("--features", type=Path, default=_features_path())
    args = parser.parse_args(argv)
    try:
        config_changed, features_changed = migrate(args.config, args.features)
    except UpdateError as error:
        logger.error("配置迁移失败: %s", error)
        return 1
    logger.info(
        "配置迁移完成（config.yml: %s，features.yml: %s）",
        "已更新" if config_changed else "无需更新",
        "已更新" if features_changed else "无需更新",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
