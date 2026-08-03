"""配置加载：从 config.yml 读取业务配置。

查找顺序：
1. 环境变量 QQBOT_CONFIG 指定路径
2. 工作目录 config.yml（生产环境部署位置）
3. 仓库根目录 config.yml（源码开发）

.env 仅保留 NoneBot 框架必需配置（driver、适配器连接等）。
"""

import os
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def find_config_path() -> Path:
    env_path = os.getenv("QQBOT_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    cwd_config = Path.cwd() / "config.yml"
    if cwd_config.exists():
        return cwd_config
    return _REPO_ROOT / "config.yml"


CONFIG_PATH = find_config_path()
_EXAMPLE_PATH = _REPO_ROOT / "config.yml.example"


def _bootstrap_from_example() -> None:
    """首次运行：config.yml 不存在时从模板自动生成。"""
    if _EXAMPLE_PATH.exists():
        try:
            import shutil

            shutil.copyfile(_EXAMPLE_PATH, CONFIG_PATH)
        except OSError:
            pass


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        _bootstrap_from_example()
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


CONFIG: dict[str, Any] = load_config()
