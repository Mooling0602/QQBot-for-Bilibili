"""版本号：安装元数据版本 + git commit 短 hash。

显示格式：
- 源码运行：<版本>-<commit短hash>（如 0.1.0-a7d65ce）
- 构建产物（release 打包）：仅 <版本>（如 0.1.0），不显示 hash
"""

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
def get_version() -> str:
    """完整版本号：源码运行 0.1.0-<hash>，构建产物 0.1.0。"""
    try:
        base = version(DIST_NAME)
    except PackageNotFoundError:
        base = "0.0.0"
    commit = _git_commit()
    return f"{base}-{commit}" if commit else base
