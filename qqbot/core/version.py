"""版本与发布渠道判定。

源码工作区始终优先显示 HEAD 的短 hash；发布镜像没有 ``.git``，由 CI 在
tag 构建时注入 ``QQBOT_RELEASE_TAG``。只有该值与安装包版本一致时才是稳定版。
"""

import os
import subprocess
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

DIST_NAME = "qqbot-for-bilibili"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _git_commit() -> str | None:
    """源码运行：从 git 读取 HEAD 短 hash（构建产物无 .git，返回 None）。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


@lru_cache(maxsize=1)
def get_base_version() -> str:
    """从安装元数据读取基础版本号。"""
    try:
        return version(DIST_NAME)
    except PackageNotFoundError:
        return "0.0.0"


@lru_cache(maxsize=1)
def get_version() -> str:
    """完整版本号：源码运行追加 HEAD 短 hash，构建产物只显示基础版本。"""
    base = get_base_version()
    commit = _git_commit()
    return f"{base}-{commit}" if commit else base


def get_status_version() -> str:
    """返回供状态命令展示的版本与发布渠道。"""
    base = get_base_version()
    commit = _git_commit()
    if commit:
        return f"v{base} (git: {commit})"
    if os.getenv("QQBOT_RELEASE_TAG") == base:
        return f"v{base} (stable)"
    return f"v{base} (git)"
