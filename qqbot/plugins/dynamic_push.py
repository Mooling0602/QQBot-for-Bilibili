"""按群订阅时间推送关注时间线中的新动态。"""

import asyncio
import base64
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bilibili_feed_api import (
    BiliClient,
    DynamicWatcher,
    FeedAllWatcher,
    is_following,
)
from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from qqbot.core import features
from qqbot.core.config import CONFIG
from qqbot.core.group_config import (
    GROUP_CONFIG_ROOT,
    load_group_config,
    save_group_config,
)
from qqbot.core.onebot import get_onebot_bot
from qqbot.core.screenshot import fetch_dynamic_screenshot
from qqbot.core.service_mute import is_group_muted

driver = get_driver()

FEATURE_KEY = "dynamic_push"
DEFAULT_PROMPT = "你关注的 UP 主发布了新动态～"
DYNAMIC_URL = "https://t.bilibili.com/{id}"
SCREENSHOT_CACHE_MAX_ITEMS = 128
FOLLOWING_RECHECK_SEC = 600
LOCAL_TZ = datetime.now().astimezone().tzinfo or timezone(timedelta(hours=8))

# dry-run：只记录日志不实际发送（调试用）
DRY_RUN = bool(CONFIG.get("push_dry_run", False))
# 动态监听总开关（config.yml dynamic_monitor）
MONITOR_ENABLED = bool(CONFIG.get("dynamic_monitor", False))

_BILIBILI_CONFIG = CONFIG.get("bilibili") or {}
_SCREENSHOT_URL = (CONFIG.get("screenshot") or {}).get("url", "")


@dataclass(frozen=True)
class Subscription:
    group_id: str
    subscribed_at: float


@dataclass(frozen=True)
class DynamicNotice:
    dynamic_id: str
    mid: str
    published_at: float
    title: str

    @property
    def url(self) -> str:
        return DYNAMIC_URL.format(id=self.dynamic_id)


@dataclass(frozen=True)
class FollowingStatus:
    follows: bool
    checked_at: float


_mid_locks: dict[str, asyncio.Lock] = {}
_screenshot_cache: OrderedDict[str, bytes] = OrderedDict()
_screenshot_tasks: dict[str, asyncio.Task[bytes]] = {}
_screenshot_lock = asyncio.Lock()
_following_status: dict[str, FollowingStatus] = {}


def _as_timestamp(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    return timestamp if timestamp > 0 else None


def _as_mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _published_at(item: dict) -> float | None:
    modules = _as_mapping(item.get("modules"))
    author = _as_mapping(modules.get("module_author"))
    return _as_timestamp(author.get("pub_ts"))


def _collect_watch() -> dict[str, list[Subscription]]:
    """扫描群配置，返回 mid 到群订阅起点的映射。

    旧配置没有订阅时间时，在首次发现时以当前时间补齐，避免升级后推送历史动态。
    """
    watch: dict[str, list[Subscription]] = {}
    if not GROUP_CONFIG_ROOT.exists():
        return watch

    now = time.time()
    for group_dir in GROUP_CONFIG_ROOT.iterdir():
        if not group_dir.is_dir():
            continue
        group_id = group_dir.name
        cfg = load_group_config(group_id)
        item = cfg.get(FEATURE_KEY) or {}
        if not isinstance(item, dict) or not item.get("enable"):
            continue

        mids = [str(mid).strip() for mid in item.get("mids") or []]
        mids = [mid for mid in mids if mid]
        raw_times = item.get("mid_subscribed_at") or {}
        subscribed_at = dict(raw_times) if isinstance(raw_times, dict) else {}
        changed = not isinstance(raw_times, dict)

        for mid in mids:
            timestamp = _as_timestamp(subscribed_at.get(mid))
            if timestamp is None:
                timestamp = now
                subscribed_at[mid] = timestamp
                changed = True
            watch.setdefault(mid, []).append(
                Subscription(group_id=group_id, subscribed_at=timestamp)
            )

        active_mids = set(mids)
        stale_mids = set(subscribed_at) - active_mids
        if stale_mids:
            for mid in stale_mids:
                subscribed_at.pop(mid, None)
            changed = True

        if changed:
            updated_item = dict(item)
            updated_item["mid_subscribed_at"] = subscribed_at
            cfg[FEATURE_KEY] = updated_item
            save_group_config(group_id, cfg)

    return watch


def _group_item(group_id: str) -> dict:
    cfg = load_group_config(group_id)
    item = cfg.get(FEATURE_KEY) or {}
    return item if isinstance(item, dict) else {}


def _group_still_subscribes(group_id: str, mid: str) -> bool:
    item = _group_item(group_id)
    return bool(
        item.get("enable") and mid in {str(value) for value in item.get("mids") or []}
    )


def _extract_title(item: dict) -> str | None:
    modules = _as_mapping(item.get("modules"))
    dynamic = _as_mapping(modules.get("module_dynamic"))
    major = _as_mapping(dynamic.get("major"))
    candidates = (
        _as_mapping(major.get("archive")).get("title"),
        _as_mapping(major.get("article")).get("title"),
        _as_mapping(major.get("opus")).get("title"),
        _as_mapping(dynamic.get("desc")).get("text"),
    )
    for candidate in candidates:
        if isinstance(candidate, str):
            title = " ".join(candidate.split())
            if title:
                return title[:120]
    return None


def _build_notice(mid: str, item: dict) -> DynamicNotice | None:
    dynamic_id = str(item.get("id_str") or "").strip()
    published_at = _published_at(item)
    title = _extract_title(item)
    if not dynamic_id or published_at is None or not title:
        return None
    return DynamicNotice(
        dynamic_id=dynamic_id,
        mid=mid,
        published_at=published_at,
        title=title,
    )


def _candidate_id(item: dict) -> str:
    return str(item.get("id_str") or "").strip()


def _format_published_at(
    published_at: float, *, now: datetime | None = None
) -> str | None:
    """Render a dynamic publication time in the deployment's local timezone."""
    try:
        published = datetime.fromtimestamp(published_at, tz=LOCAL_TZ)
        local_now = (
            now.astimezone(LOCAL_TZ) if now is not None else datetime.now(LOCAL_TZ)
        )
        days_ago = (local_now.date() - published.date()).days
    except (OverflowError, OSError, ValueError) as error:
        logger.warning(f"动态发布时间格式化失败（{published_at}）: {error}")
        return None

    if days_ago == 0:
        day = "今天"
    elif days_ago == 1:
        day = "昨天"
    elif days_ago == 2:
        day = "前天"
    else:
        day = f"{published.year}年{published.month:02d}月{published.day:02d}日"
    return f"{day} {published.hour:02d}:{published.minute:02d}"


async def _get_screenshot(dynamic_id: str) -> bytes:
    """获取同一动态的共享截图，合并并发请求并保留有限的内存缓存。"""
    async with _screenshot_lock:
        cached = _screenshot_cache.get(dynamic_id)
        if cached is not None:
            _screenshot_cache.move_to_end(dynamic_id)
            return cached

        task = _screenshot_tasks.get(dynamic_id)
        if task is None:
            task = asyncio.create_task(
                fetch_dynamic_screenshot(dynamic_id, remote_url=_SCREENSHOT_URL or None)
            )
            _screenshot_tasks[dynamic_id] = task

    try:
        screenshot = await task
        if not screenshot:
            raise RuntimeError("截图服务返回空内容")
        async with _screenshot_lock:
            _screenshot_cache[dynamic_id] = screenshot
            _screenshot_cache.move_to_end(dynamic_id)
            while len(_screenshot_cache) > SCREENSHOT_CACHE_MAX_ITEMS:
                _screenshot_cache.popitem(last=False)
        return screenshot
    finally:
        if task.done():
            async with _screenshot_lock:
                if _screenshot_tasks.get(dynamic_id) is task:
                    _screenshot_tasks.pop(dynamic_id, None)


async def _send_to_group(
    bot: Bot,
    group_id: str,
    notice: DynamicNotice,
    screenshot: bytes | None,
) -> bool:
    """发送完整动态消息；没有截图时强制附加直链。"""
    if is_group_muted(group_id):
        logger.info(f"群 {group_id} 已静默，跳过动态 {notice.dynamic_id} 推送")
        return True
    if not _group_still_subscribes(group_id, notice.mid):
        return True

    group_cfg = _group_item(group_id)
    prompt = (
        group_cfg.get("prompt")
        or features.feature_prompt(FEATURE_KEY)
        or DEFAULT_PROMPT
    )
    add_url = bool(group_cfg.get("add_url", features.feature_add_url(FEATURE_KEY)))

    message = Message(prompt)
    message += Message(f"\n{notice.title}")
    if screenshot is not None:
        message += MessageSegment.image(
            f"base64://{base64.b64encode(screenshot).decode()}"
        )
    if screenshot is None:
        if published_at := _format_published_at(notice.published_at):
            message += Message(f"\n发布时间：{published_at}")
        message += Message(f"\n{notice.url}")
    elif add_url:
        message += Message(f"\n{notice.url}")

    if DRY_RUN:
        logger.info(f"[dry-run] 将推送到群 {group_id}: {message}")
        return True
    try:
        await bot.call_api("send_group_msg", group_id=int(group_id), message=message)
        logger.info(f"已推送动态到群 {group_id}: {notice.dynamic_id}")
        return True
    except Exception as error:  # noqa: BLE001
        logger.error(f"推送群 {group_id} 动态 {notice.dynamic_id} 失败: {error}")
        return False


async def _send_parse_error(bot: Bot, group_id: str, dynamic_id: str) -> bool:
    """对可判定为订阅后新动态、但内容无法解析的情况作一次简短提示。"""
    if is_group_muted(group_id):
        logger.info(f"群 {group_id} 已静默，跳过动态 {dynamic_id} 解析错误通知")
        return True
    if DRY_RUN:
        logger.info(f"[dry-run] 群 {group_id} 动态 {dynamic_id} 内容解析失败")
        return True
    try:
        await bot.call_api(
            "send_group_msg",
            group_id=int(group_id),
            message=Message("检测到一条新动态，但内容解析失败，请管理员检查。"),
        )
        return True
    except Exception as error:  # noqa: BLE001
        logger.error(f"通知群 {group_id} 动态 {dynamic_id} 解析失败时出错: {error}")
        return False


def _mid_lock(mid: str) -> asyncio.Lock:
    return _mid_locks.setdefault(mid, asyncio.Lock())


async def _resolve_dynamic_sources(
    client: BiliClient,
    mids: list[str],
    *,
    now: float | None = None,
) -> tuple[list[str], list[str]]:
    """Choose feed/all for followed uploaders and feed/space for the rest.

    Following relationships are refreshed periodically so a manual follow takes
    effect without restarting the bot, while avoiding one relation request per
    polling cycle and MID.
    """
    normalized_mids = list(dict.fromkeys(str(mid) for mid in mids))
    if not client.has_sessdata:
        return [], normalized_mids

    checked_now = time.time() if now is None else now
    to_check = [
        mid
        for mid in normalized_mids
        if (status := _following_status.get(mid)) is None
        or checked_now - status.checked_at >= FOLLOWING_RECHECK_SEC
    ]

    async def check_following(mid: str) -> None:
        previous = _following_status.get(mid)
        try:
            follows = await is_following(client, mid)
        except Exception as error:
            logger.warning(f"检查 mid {mid} 的关注关系失败: {error}")
            raise

        _following_status[mid] = FollowingStatus(
            follows=follows,
            checked_at=checked_now,
        )
        if not follows and (previous is None or previous.follows):
            logger.warning(
                f"登录账号未关注 mid {mid}；请使用该 B 站账号手动关注后再等待状态复查，"
                "当前将回退到 feed/space。"
            )
        elif follows and previous is not None and not previous.follows:
            logger.info(f"mid {mid} 已被登录账号手动关注，切换至 feed/all")

    if to_check:
        await asyncio.gather(*(check_following(mid) for mid in to_check))

    feed_all_mids = [mid for mid in normalized_mids if _following_status[mid].follows]
    feed_space_mids = [
        mid for mid in normalized_mids if not _following_status[mid].follows
    ]
    return feed_all_mids, feed_space_mids


async def _fetch_candidates(
    feed_all_watcher: FeedAllWatcher,
    space_watcher: DynamicWatcher,
    feed_all_mids: list[str],
    feed_space_mids: list[str],
) -> dict[str, list[dict]]:
    """Fetch each source once per cycle and merge candidates by MID."""
    candidates: dict[str, list[dict]] = {}
    if feed_all_mids:
        try:
            candidates.update(await feed_all_watcher.fetch_unseen(feed_all_mids))
        except Exception as error:
            logger.warning(f"feed/all 轮询失败: {error}")
            raise

    if not feed_space_mids:
        return candidates

    space_results = await asyncio.gather(
        *(space_watcher.fetch_unseen(mid) for mid in feed_space_mids),
        return_exceptions=True,
    )
    for mid, result in zip(feed_space_mids, space_results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                f"feed/space 查询 mid {mid} 失败: {result}；"
                "请检查服务器网络环境或稍后重试。"
            )
            raise result
        if result:
            candidates[mid] = result
    return candidates


async def _process_mid(
    watcher: FeedAllWatcher | DynamicWatcher,
    mid: str,
    items: list[dict],
) -> None:
    """同一 mid 的候选动态串行处理，不同 mid 可并行。"""
    async with _mid_lock(mid):
        for item in items:
            dynamic_id = _candidate_id(item)
            if not dynamic_id:
                continue

            published_at = _published_at(item)
            if published_at is None:
                logger.warning(f"动态 {dynamic_id} 缺少发布时间，无法判定订阅范围")
                watcher.acknowledge(mid, [dynamic_id])
                continue

            # 每条候选动态重新读取订阅快照，避免配置命令与轮询交错时遗漏新订阅的群。
            subscriptions = _collect_watch().get(mid, [])
            targets = [
                subscription
                for subscription in subscriptions
                if published_at > subscription.subscribed_at
            ]
            if not targets:
                watcher.acknowledge(mid, [dynamic_id])
                continue

            bot = _pick_bot()
            if not bot:
                logger.warning(
                    f"动态 {dynamic_id} 到达时没有可用 OneBot 机器人，将在下轮重试"
                )
                return

            notice = _build_notice(mid, item)
            if notice is None:
                logger.warning(f"动态 {dynamic_id} 缺少可展示标题，发送解析失败提示")
                for subscription in targets:
                    await _send_parse_error(bot, subscription.group_id, dynamic_id)
                watcher.acknowledge(mid, [dynamic_id])
                continue

            screenshot: bytes | None = None
            try:
                screenshot = await _get_screenshot(notice.dynamic_id)
            except Exception as error:  # noqa: BLE001
                logger.warning(
                    f"动态 {notice.dynamic_id} 截图失败，将发送标题和直链: {error}"
                )

            for subscription in targets:
                await _send_to_group(bot, subscription.group_id, notice, screenshot)
            watcher.acknowledge(mid, [dynamic_id])


async def _poll_loop() -> None:
    client = BiliClient(
        sessdata=_BILIBILI_CONFIG.get("sessdata") or None,
        proxy=_BILIBILI_CONFIG.get("proxy") or None,
        proxy_auth=_BILIBILI_CONFIG.get("proxy_auth") or None,
    )
    interval = FeedAllWatcher.BASE_POLL_SEC
    last_poll = 0.0
    await asyncio.sleep(5)  # 等机器人就绪
    if client.has_sessdata:
        logger.info("动态推送轮询任务已启动（优先 feed/all，未关注时回退 feed/space）")
    else:
        logger.warning(
            "动态推送未配置 SESSDATA，将仅使用 feed/space；"
            "如遇 412 风控，请管理员自行检查服务器网络环境。"
        )

    # QQBot 以群订阅时间过滤历史动态，因此不能使用 watcher 的默认首轮基线。
    feed_all_watcher = FeedAllWatcher(
        client,
        mids=[],
        state_dir=Path.cwd() / "cache",
        baseline_first=False,
    )
    space_watcher = DynamicWatcher(
        client,
        state_dir=Path.cwd() / "cache",
        baseline_first=False,
    )
    try:
        while True:
            try:
                watch = _collect_watch()
                if not watch:
                    await asyncio.sleep(5)
                    continue

                now = time.time()
                if now - last_poll >= interval:
                    last_poll = now
                    mids = list(watch)
                    feed_all_mids, feed_space_mids = await _resolve_dynamic_sources(
                        client,
                        mids,
                        now=now,
                    )
                    candidates = await _fetch_candidates(
                        feed_all_watcher,
                        space_watcher,
                        feed_all_mids,
                        feed_space_mids,
                    )
                    tasks = [
                        _process_mid(
                            feed_all_watcher if mid in feed_all_mids else space_watcher,
                            mid,
                            items,
                        )
                        for mid, items in candidates.items()
                    ]
                    if tasks:
                        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                        for outcome in outcomes:
                            if isinstance(outcome, Exception):
                                logger.error(f"动态处理任务失败: {outcome}")
                    interval = FeedAllWatcher.BASE_POLL_SEC
            except Exception as error:  # noqa: BLE001
                interval = min(interval * 2, FeedAllWatcher.MAX_POLL_SEC)
                logger.warning(f"动态轮询失败: {error}，退避至 {interval}s")
            await asyncio.sleep(1)
    finally:
        await client.close()


def _pick_bot() -> Bot | None:
    """取一个已连接的 OneBot 机器人。"""
    return get_onebot_bot()


@driver.on_startup
async def _start_poller() -> None:
    if not MONITOR_ENABLED:
        logger.info("动态监听已禁用（config.yml dynamic_monitor=false）")
        return
    asyncio.create_task(_poll_loop())
