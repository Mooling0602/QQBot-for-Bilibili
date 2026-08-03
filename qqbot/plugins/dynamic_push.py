"""动态推送：轮询已开启 dynamic_push 的群所关注的 UP 主，新动态推送到群。

- 后台 asyncio 任务（机器人启动时开始）
- 轮询间隔：10s 基础，出错翻倍退避（上限 160s），各 mid 独立
- 群配置：config/<群号>/config.yml → dynamic_push.{enable, mids, prompt, add_url}
- 新动态：截图 → 组装消息（prompt + 图片 + 摘要 + 直链）→ 发送到对应群
"""

import asyncio
import base64
import time
from pathlib import Path

from bilibili_feed_api.client import BiliClient
from bilibili_feed_api.dynamic import DynamicWatcher
from bilibili_feed_api.feed_all_watcher import FeedAllWatcher
from bilibili_feed_api.screenshot import fetch_screenshot
from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from qqbot.core import features
from qqbot.core.config import CONFIG
from qqbot.core.group_config import GROUP_CONFIG_ROOT, load_group_config

driver = get_driver()

FEATURE_KEY = "dynamic_push"
DEFAULT_PROMPT = "你关注的 UP 主发布了新动态～"
DYNAMIC_URL = "https://t.bilibili.com/{id}"

# dry-run：只记录日志不实际发送（调试用）
DRY_RUN = bool(CONFIG.get("push_dry_run", False))
# 动态监听总开关（config.yml dynamic_monitor）
MONITOR_ENABLED = bool(CONFIG.get("dynamic_monitor", False))

_BILIBILI_CONFIG = CONFIG.get("bilibili") or {}
_SCREENSHOT_URL = (CONFIG.get("screenshot") or {}).get("url", "")


def _collect_watch() -> dict[str, list[str]]:
    """扫描全部群配置，返回 mid → 启用了该功能的群列表。"""
    watch: dict[str, list[str]] = {}
    if not GROUP_CONFIG_ROOT.exists():
        return watch
    for group_dir in GROUP_CONFIG_ROOT.iterdir():
        if not group_dir.is_dir():
            continue
        group_id = group_dir.name
        cfg = load_group_config(group_id)
        item = cfg.get(FEATURE_KEY) or {}
        if not item.get("enable"):
            continue
        for mid in item.get("mids") or []:
            watch.setdefault(str(mid), []).append(group_id)
    return watch


def _group_item(group_id: str) -> dict:
    cfg = load_group_config(group_id)
    return cfg.get(FEATURE_KEY) or {}


async def _send_to_group(bot: Bot, group_id: str, mid: str, item: dict) -> None:
    group_cfg = _group_item(group_id)
    prompt = (
        group_cfg.get("prompt")
        or features.feature_prompt(FEATURE_KEY)
        or DEFAULT_PROMPT
    )
    add_url = bool(group_cfg.get("add_url", features.feature_add_url(FEATURE_KEY)))

    messages = Message(prompt)
    # 截图成功：只发图片；截图失败：用文字描述兜底
    try:
        png = await fetch_screenshot(
            item["id_str"], remote_url=_SCREENSHOT_URL or None
        )
        messages += MessageSegment.image(f"base64://{base64.b64encode(png).decode()}")
    except Exception as e:
        logger.warning(f"群 {group_id} 动态截图失败: {e}")
        messages += Message(DynamicWatcher.describe(item))
    if add_url:
        messages += Message(f"\n{DYNAMIC_URL.format(id=item['id_str'])}")

    if DRY_RUN:
        logger.info(f"[dry-run] 将推送到群 {group_id}: {messages}")
        return
    try:
        await bot.call_api("send_group_msg", group_id=int(group_id), message=messages)
        logger.info(f"已推送动态到群 {group_id}: {item.get('id_str')}")
    except Exception as e:
        logger.error(f"推送群 {group_id} 失败: {e}")


async def _poll_loop() -> None:
    client = BiliClient(
        sessdata=_BILIBILI_CONFIG.get("sessdata") or None,
        proxy=_BILIBILI_CONFIG.get("proxy") or None,
        proxy_auth=_BILIBILI_CONFIG.get("proxy_auth") or None,
    )
    await asyncio.sleep(5)  # 等机器人就绪

    async def on_new(mid: str, item: dict) -> None:
        watch = _collect_watch()
        groups = watch.get(mid, [])
        if not groups:
            return
        logger.info(f"UP {mid} 新动态 {item.get('id_str')}，推送到群 {groups}")
        for group_id in groups:
            bot = _pick_bot()
            if bot:
                await _send_to_group(bot, group_id, mid, item)

    watcher = FeedAllWatcher(
        client, mids=[], state_dir=Path.cwd() / "cache", on_new=on_new
    )
    interval = FeedAllWatcher.BASE_POLL_SEC
    last_poll = 0.0
    logger.info("动态推送轮询任务已启动（feed/all）")

    while True:
        try:
            watch = _collect_watch()
            mids = list(watch.keys())
            if not mids:
                await asyncio.sleep(5)
                continue
            watcher._mids = mids  # 动态同步目标 mid（群配置可能变化）
            now = time.time()
            if now - last_poll >= interval:
                last_poll = now
                await watcher.poll()
                interval = FeedAllWatcher.BASE_POLL_SEC
        except Exception as e:
            interval = min(interval * 2, FeedAllWatcher.MAX_POLL_SEC)
            logger.warning(f"feed/all 轮询失败: {e}，退避至 {interval}s")
        await asyncio.sleep(1)


def _pick_bot() -> Bot | None:
    """取一个已连接的 OneBot 机器人。"""
    try:
        from nonebot import get_bots

        for bot in get_bots().values():
            if bot.type == "OneBot V11" or "OneBot" in str(bot.type):
                return bot  # type: ignore
    except Exception:
        pass
    return None


@driver.on_startup
async def _start_poller() -> None:
    if not MONITOR_ENABLED:
        logger.info("动态监听已禁用（config.yml dynamic_monitor=false）")
        return
    asyncio.create_task(_poll_loop())
