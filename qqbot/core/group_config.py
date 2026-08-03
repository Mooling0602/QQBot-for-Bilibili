"""群级配置：每个群独立的配置存储（config/<群号>/config.yml）。

目录自动创建于工作目录下（cwd/config/），已被 .gitignore 排除。
配置结构按功能模块扩展，见模板 _TEMPLATE。
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger("qqbot.group_config")

# 群配置根目录（工作目录下）
GROUP_CONFIG_ROOT = Path.cwd() / "config"

# 群配置模板（新群首次访问时自动生成）
_TEMPLATE = """\
# 群 {group_id} 配置
# 通过 @机器人 /群配置 命令查看和修改

group_id: {group_id}

# ===== 功能配置（按需扩展）=====
"""


def get_group_config_path(group_id: str | int) -> Path:
    """返回群配置目录路径（不存在时自动创建）。"""
    group_dir = GROUP_CONFIG_ROOT / str(group_id)
    group_dir.mkdir(parents=True, exist_ok=True)
    return group_dir / "config.yml"


def load_group_config(group_id: str | int) -> dict:
    """加载群配置；首次访问自动创建默认配置。"""
    path = get_group_config_path(group_id)
    if not path.exists():
        path.write_text(_TEMPLATE.format(group_id=group_id), encoding="utf-8")
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.error(f"群 {group_id} 配置解析失败: {e}")
        return {"group_id": str(group_id)}


def save_group_config(group_id: str | int, data: dict) -> None:
    """保存群配置。"""
    path = get_group_config_path(group_id)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def get_group_id(event) -> str | None:
    """从事件提取群号（非群聊事件返回 None）。"""
    return str(getattr(event, "group_id", "") or "") or None
