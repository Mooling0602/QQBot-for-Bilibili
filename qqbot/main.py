"""QQ 机器人入口。

启动（源码开发，从项目根）：
    uv run python -m qqbot.main
构建产物（wheel 安装）后：
    qqbot 命令或 python -m qqbot.bot

入口以包模块方式运行，不依赖源码目录结构：
- 配置（.env / config.yml）：优先工作目录，其次包内（源码开发）
- 插件：按包模块名自动发现加载（qqbot.plugins.*），不依赖文件路径
"""

import os
import pkgutil
import ssl
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env：优先工作目录，其次仓库根目录（源码开发时 .env 位于项目根）
_cwd_env = Path.cwd() / ".env"
_repo_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_cwd_env if _cwd_env.exists() else _repo_env)

from qqbot.core.config import CONFIG


def _inject_framework_config() -> None:
    """将 config.yml 的适配器/框架配置注入环境变量（须在 init() 前调用）。"""
    import json

    fw = CONFIG.get("framework", {})
    if fw.get("driver"):
        os.environ["DRIVER"] = fw["driver"]

    qq = CONFIG.get("qq_official", {})
    if "bots" in qq:
        os.environ["QQ_BOTS"] = json.dumps(qq.get("bots", []), ensure_ascii=False)
    os.environ["QQ_IS_SANDBOX"] = str(bool(qq.get("sandbox", False))).lower()

    ob = CONFIG.get("onebot", {})
    if ob.get("ws_urls"):
        os.environ["ONEBOT_WS_URLS"] = json.dumps(ob["ws_urls"])


_inject_framework_config()

# uv 自带的 Python 默认不加载系统 CA（cafile=None），
# 若系统默认 CA 文件缺失，显式指定常见路径，避免 SSL 验证失败。
if not os.environ.get("SSL_CERT_FILE") and not ssl.get_default_verify_paths().cafile:
    for candidate in (
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/ssl/certs/ca-bundle.crt",
    ):
        if os.path.exists(candidate):
            os.environ["SSL_CERT_FILE"] = candidate
            break

from nonebot import get_driver, init, load_plugin
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebot.adapters.qq import Adapter as QQAdapter

import qqbot.plugins

init()

driver = get_driver()
# 双适配器：QQ 官方 API（adapter-qq，保留备用）+ OneBot v11（NapCat）
driver.register_adapter(QQAdapter)
driver.register_adapter(OneBotV11Adapter)

# 按包模块名自动发现并加载插件（qqbot.plugins.*），与文件路径/工作目录解耦
for module_info in pkgutil.iter_modules(qqbot.plugins.__path__):
    load_plugin(f"qqbot.plugins.{module_info.name}")

if __name__ == "__main__":
    from nonebot import run

    run()
