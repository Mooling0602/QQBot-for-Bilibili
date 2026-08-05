"""Push Bilibili live start and optional end notifications to subscribed groups."""

import asyncio
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bilibili_feed_api import (
    BiliClient,
    LiveStatus,
    get_live_room_info,
    get_live_status,
)
from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, Message

from qqbot.core import features
from qqbot.core.config import CONFIG
from qqbot.core.group_config import (
    GROUP_CONFIG_ROOT,
    load_group_config,
    save_group_config,
)
from qqbot.core.live_state import LiveSession, LiveState, LiveStateStore
from qqbot.core.onebot import get_onebot_bot
from qqbot.core.service_mute import is_group_muted

driver = get_driver()

FEATURE_KEY = "live_alert"
DEFAULT_OPEN_PROMPT = "你关注的 UP 主正在直播～"
DEFAULT_CLOSE_PROMPT = "你关注的 UP 主已经下播了。"
BASE_POLL_SEC = 1.0
MAX_POLL_SEC = 64.0
GLOBAL_REQUEST_INTERVAL_SEC = 0.1
LOCAL_TZ = datetime.now().astimezone().tzinfo or timezone(timedelta(hours=8))

DRY_RUN = bool(CONFIG.get("push_dry_run", False))
MONITOR_ENABLED = bool(CONFIG.get("live_monitor", False))
_BILIBILI_CONFIG = CONFIG.get("bilibili") or {}
_mid_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class Subscription:
    group_id: str
    subscribed_at: float


@dataclass
class PollSchedule:
    interval: float = BASE_POLL_SEC
    next_at: float = 0.0


class RequestPacer:
    """Evenly space requests across all MIDs at ten requests per second."""

    def __init__(self, interval: float = GLOBAL_REQUEST_INTERVAL_SEC):
        self._interval = interval
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next_at)
            self._next_at = scheduled + self._interval
        await asyncio.sleep(max(0.0, scheduled - time.monotonic()))


def _as_timestamp(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    return timestamp if timestamp > 0 else None


def _collect_watch() -> dict[str, list[Subscription]]:
    """Read live subscriptions and lazily establish group-level baselines."""
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

        mids = list(
            dict.fromkeys(
                mid
                for mid in (str(value).strip() for value in item.get("mids") or [])
                if mid
            )
        )
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

        stale_mids = set(subscribed_at) - set(mids)
        if stale_mids:
            for mid in stale_mids:
                subscribed_at.pop(mid, None)
            changed = True

        if changed:
            updated = dict(item)
            updated["mid_subscribed_at"] = subscribed_at
            cfg[FEATURE_KEY] = updated
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


def _group_notifies_on_close(group_id: str, mid: str) -> bool:
    if not _group_still_subscribes(group_id, mid):
        return False
    item = _group_item(group_id)
    return bool(
        item.get(
            "notify_on_close",
            features.feature_option(FEATURE_KEY, "notify_on_close", False),
        )
    )


def _format_timestamp(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    try:
        value = datetime.fromtimestamp(timestamp, tz=LOCAL_TZ)
    except (OverflowError, OSError, ValueError) as error:
        logger.warning(f"直播事件时间格式化失败（{timestamp}）: {error}")
        return None
    return value.strftime("%Y-%m-%d %H:%M")


def _area_text(session: LiveSession) -> str | None:
    parts = [part for part in (session.parent_area_name, session.area_name) if part]
    return " / ".join(dict.fromkeys(parts)) or None


def _room_url(session: LiveSession) -> str | None:
    if not session.room_id:
        return None
    return f"https://live.bilibili.com/{session.room_id}"


def _open_message(group_id: str, session: LiveSession) -> Message:
    item = _group_item(group_id)
    prompt = (
        item.get("prompt")
        or features.feature_prompt(FEATURE_KEY)
        or DEFAULT_OPEN_PROMPT
    )
    message = Message(str(prompt))
    if session.title:
        message += Message(f"\n{session.title}")
    if area := _area_text(session):
        message += Message(f"\n分区：{area}")
    if session.live_time:
        message += Message(f"\n开播时间：{session.live_time}")
    if item.get("add_url", features.feature_add_url(FEATURE_KEY)) and (
        url := _room_url(session)
    ):
        message += Message(f"\n{url}")
    return message


def _close_message(group_id: str, session: LiveSession) -> Message:
    item = _group_item(group_id)
    prompt = (
        item.get("prompt_on_close")
        or features.feature_option(FEATURE_KEY, "prompt_on_close", "")
        or DEFAULT_CLOSE_PROMPT
    )
    message = Message(str(prompt))
    if session.title:
        message += Message(f"\n{session.title}")
    if area := _area_text(session):
        message += Message(f"\n分区：{area}")
    if session.live_time:
        message += Message(f"\n开播时间：{session.live_time}")
    if closed_at := _format_timestamp(session.closed_at):
        message += Message(f"\n下播时间：{closed_at}")
    if item.get("add_url", features.feature_add_url(FEATURE_KEY)) and (
        url := _room_url(session)
    ):
        message += Message(f"\n{url}")
    return message


async def _send_open(bot: Bot, group_id: str, mid: str, session: LiveSession) -> bool:
    if is_group_muted(group_id):
        logger.info(f"群 {group_id} 已静默，跳过 mid {mid} 的开播消息")
        return True
    if not _group_still_subscribes(group_id, mid):
        return True
    message = _open_message(group_id, session)
    if DRY_RUN:
        logger.info(f"[dry-run] 将推送开播消息到群 {group_id}: {message}")
        return True
    try:
        await bot.call_api("send_group_msg", group_id=int(group_id), message=message)
        logger.info(f"已推送 mid {mid} 的开播消息到群 {group_id}")
        return True
    except Exception as error:  # noqa: BLE001
        logger.error(f"推送群 {group_id} 的开播消息失败: {error}")
        return False


async def _send_close(bot: Bot, group_id: str, mid: str, session: LiveSession) -> bool:
    if is_group_muted(group_id):
        logger.info(f"群 {group_id} 已静默，跳过 mid {mid} 的下播消息")
        return True
    if not _group_notifies_on_close(group_id, mid):
        return True
    message = _close_message(group_id, session)
    if DRY_RUN:
        logger.info(f"[dry-run] 将推送下播消息到群 {group_id}: {message}")
        return True
    try:
        await bot.call_api("send_group_msg", group_id=int(group_id), message=message)
        logger.info(f"已推送 mid {mid} 的下播消息到群 {group_id}")
        return True
    except Exception as error:  # noqa: BLE001
        logger.error(f"推送群 {group_id} 的下播消息失败: {error}")
        return False


def _session_from_status(
    status: LiveStatus, now: float, subscriptions: list[Subscription]
) -> LiveSession:
    targets = list(
        dict.fromkeys(
            subscription.group_id
            for subscription in subscriptions
            if subscription.subscribed_at < now
        )
    )
    room_key = str(status.room_id) if status.room_id else "unknown"
    return LiveSession(
        session_id=f"{room_key}:{int(now * 1000)}",
        room_id=status.room_id,
        opened_at=now,
        title=status.title,
        detail_retry_at=now if targets and status.room_id else None,
        open_targets=targets,
    )


def _apply_details(session: LiveSession, status: LiveStatus) -> None:
    session.title = status.title or session.title
    session.live_time = status.live_time
    session.area_name = status.area_name
    session.parent_area_name = status.parent_area_name
    if status.room_id:
        session.room_id = status.room_id
    if session.room_id and session.live_time:
        session.session_id = f"{session.room_id}:{session.live_time}"


async def _refresh_details(
    client: BiliClient,
    session: LiveSession,
    pacer: RequestPacer,
    now: float,
) -> bool:
    if session.detail_retry_at is None or session.detail_retry_at > now:
        return False
    if not session.room_id:
        session.detail_retry_at = None
        return True
    try:
        await pacer.acquire()
        details = await get_live_room_info(client, session.room_id)
    except Exception as error:  # noqa: BLE001
        session.detail_retry_interval = min(
            session.detail_retry_interval * 2, MAX_POLL_SEC
        )
        jitter = random.uniform(0.9, 1.1)
        session.detail_retry_at = now + min(
            session.detail_retry_interval * jitter, MAX_POLL_SEC
        )
        logger.warning(
            f"直播间 {session.room_id} 详情查询失败，"
            f"将在 {session.detail_retry_interval:.0f}s 后重试: {error}"
        )
        return True

    _apply_details(session, details)
    session.detail_retry_at = None
    session.detail_retry_interval = BASE_POLL_SEC
    return True


async def _deliver_open(
    mid: str,
    state: LiveState,
    store: LiveStateStore,
) -> None:
    session = state.active
    if session is None:
        return
    pending = [
        group_id
        for group_id in session.open_targets
        if group_id not in session.open_sent
    ]
    if not pending:
        return
    bot = get_onebot_bot()
    if bot is None:
        logger.warning(f"mid {mid} 开播时没有可用 OneBot 机器人，将在下轮重试")
        return
    for group_id in pending:
        if await _send_open(bot, group_id, mid, session):
            session.open_sent.append(group_id)
            store.save(mid, state)


async def _deliver_close(
    mid: str,
    state: LiveState,
    store: LiveStateStore,
) -> None:
    if not state.closing:
        return
    bot = get_onebot_bot()
    if bot is None:
        logger.warning(f"mid {mid} 下播时没有可用 OneBot 机器人，将在下轮重试")
        return
    for session in list(state.closing):
        pending = [
            group_id
            for group_id in session.close_targets
            if group_id not in session.close_sent
        ]
        for group_id in pending:
            if await _send_close(bot, group_id, mid, session):
                session.close_sent.append(group_id)
                store.save(mid, state)
        if all(group_id in session.close_sent for group_id in session.close_targets):
            state.closing.remove(session)
            store.save(mid, state)


async def _handle_status(
    client: BiliClient,
    mid: str,
    status: LiveStatus,
    subscriptions: list[Subscription],
    store: LiveStateStore,
    pacer: RequestPacer,
    now: float,
) -> None:
    state = store.load(mid)
    if state is None:
        # Never announce a stream that began before this MID was first observed.
        state = LiveState(last_status=status.live_status)
        if status.is_live:
            state.active = _session_from_status(status, now, [])
        store.save(mid, state)
        return

    if status.is_live:
        if state.last_status != 1:
            state.active = _session_from_status(status, now, subscriptions)
            state.last_status = 1
            store.save(mid, state)
        elif state.active is None:
            # A damaged legacy cache must be treated as a silent baseline.
            state.active = _session_from_status(status, now, [])
            store.save(mid, state)

        session = state.active
        if session is not None and await _refresh_details(client, session, pacer, now):
            store.save(mid, state)
        await _deliver_open(mid, state, store)
        await _deliver_close(mid, state, store)
        return

    if state.last_status == 1:
        active = state.active
        state.last_status = status.live_status
        state.active = None
        if active is not None:
            active.closed_at = now
            active.close_targets = [
                group_id
                for group_id in active.open_sent
                if _group_notifies_on_close(group_id, mid)
            ]
            active.close_sent = []
            if active.close_targets:
                state.closing.append(active)
        store.save(mid, state)
    elif state.last_status != status.live_status:
        state.last_status = status.live_status
        store.save(mid, state)
    await _deliver_close(mid, state, store)


def _mid_lock(mid: str) -> asyncio.Lock:
    return _mid_locks.setdefault(mid, asyncio.Lock())


async def _poll_mid(
    client: BiliClient,
    mid: str,
    subscriptions: list[Subscription],
    store: LiveStateStore,
    pacer: RequestPacer,
) -> None:
    async with _mid_lock(mid):
        await pacer.acquire()
        status = await get_live_status(client, mid)
        await _handle_status(
            client,
            mid,
            status,
            subscriptions,
            store,
            pacer,
            time.time(),
        )


async def _poll_loop() -> None:
    client = BiliClient(
        sessdata=_BILIBILI_CONFIG.get("sessdata") or None,
        proxy=_BILIBILI_CONFIG.get("proxy") or None,
        proxy_auth=_BILIBILI_CONFIG.get("proxy_auth") or None,
    )
    store = LiveStateStore(Path.cwd() / "cache")
    pacer = RequestPacer()
    schedules: dict[str, PollSchedule] = {}
    await asyncio.sleep(5)
    logger.info("直播提醒轮询任务已启动（每 MID 1s，失败退避上限 64s）")
    try:
        while True:
            watch = _collect_watch()
            for mid in set(schedules) - set(watch):
                schedules.pop(mid, None)
            now = time.monotonic()
            for mid in watch:
                schedules.setdefault(mid, PollSchedule(next_at=now))

            due = [
                mid for mid, schedule in schedules.items() if schedule.next_at <= now
            ]
            if not due:
                await asyncio.sleep(0.1)
                continue

            outcomes = await asyncio.gather(
                *(_poll_mid(client, mid, watch[mid], store, pacer) for mid in due),
                return_exceptions=True,
            )
            completed_at = time.monotonic()
            for mid, outcome in zip(due, outcomes, strict=True):
                schedule = schedules.get(mid)
                if schedule is None:
                    continue
                if isinstance(outcome, BaseException):
                    schedule.interval = min(schedule.interval * 2, MAX_POLL_SEC)
                    jitter = random.uniform(0.9, 1.1)
                    schedule.next_at = completed_at + min(
                        schedule.interval * jitter, MAX_POLL_SEC
                    )
                    logger.warning(
                        f"轮询 mid {mid} 失败，退避至 {schedule.interval:.0f}s: {outcome}"
                    )
                else:
                    schedule.interval = BASE_POLL_SEC
                    schedule.next_at = completed_at + BASE_POLL_SEC
    finally:
        await client.close()


@driver.on_startup
async def _start_poller() -> None:
    if not MONITOR_ENABLED:
        logger.info("直播监听已禁用（config.yml live_monitor=false）")
        return
    asyncio.create_task(_poll_loop())
