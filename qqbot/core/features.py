"""功能选项定义：读取根配置 features.yml（仓库根目录）。

群配置可修改的键必须在此定义（白名单），否则修改失败。
选项结构：{enable: 默认开关, description: 说明, mids: 默认 B 站 mid 列表}。
"""

import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("qqbot.features")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def find_features_path() -> Path:
    env_path = os.getenv("QQBOT_FEATURES")
    if env_path:
        return Path(env_path).expanduser().resolve()
    cwd_config = Path.cwd() / "features.yml"
    if cwd_config.exists():
        return cwd_config
    return _REPO_ROOT / "features.yml"


FEATURES_PATH = find_features_path()


def load_features() -> dict:
    """返回 features 节：{键: {default, description}}。"""
    if not FEATURES_PATH.exists():
        logger.error(f"根配置缺失: {FEATURES_PATH}")
        return {}
    try:
        with open(FEATURES_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("features", {}) or {}
    except yaml.YAMLError as e:
        logger.error(f"根配置解析失败: {e}")
        return {}


_FEATURES = load_features()


def feature_keys() -> list[str]:
    """全部可用配置键。"""
    return list(_FEATURES.keys())


def is_supported(key: str) -> bool:
    """键是否在功能定义中。"""
    return key in _FEATURES


def feature_default(key: str):
    """键的默认开关值（enable）。"""
    return _FEATURES.get(key, {}).get("enable")


def feature_option(key: str, field: str, default: Any = None) -> Any:
    """Return a copy of a configurable feature field's default value."""
    item = _FEATURES.get(key, {})
    if not isinstance(item, dict) or field not in item:
        return deepcopy(default)
    return deepcopy(item[field])


def has_feature_option(key: str, field: str) -> bool:
    item = _FEATURES.get(key, {})
    return isinstance(item, dict) and field in item


def feature_mids(key: str) -> list:
    """键的默认 B 站 mid 列表（mids）。"""
    mids = feature_option(key, "mids", [])
    return mids if isinstance(mids, list) else []


def feature_description(key: str) -> str:
    return _FEATURES.get(key, {}).get("description", "")


def feature_prompt(key: str) -> str:
    """键的提示文案（prompt）。"""
    return _FEATURES.get(key, {}).get("prompt", "")


def feature_add_url(key: str) -> bool:
    """是否附加直链（add_url）。"""
    return bool(_FEATURES.get(key, {}).get("add_url", False))


def convert_value(key: str, raw: str):
    """按默认值类型转换输入值；不支持的类型/非法输入抛 ValueError。"""
    default = feature_default(key)
    if isinstance(default, bool):
        if raw.lower() in ("true", "1", "开", "on", "yes"):
            return True
        if raw.lower() in ("false", "0", "关", "off", "no"):
            return False
        raise ValueError("值需为 true/false（或 开/关）")
    if isinstance(default, int):
        return int(raw)
    return raw
