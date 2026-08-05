import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

import nonebot
from bilibili_feed_api import LiveStatus
from nonebot.adapters.onebot.v11 import Bot

nonebot.init()

from qqbot.core import service_mute
from qqbot.core.live_state import LiveSession, LiveState, LiveStateStore
from qqbot.plugins import live_alert


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def call_api(self, _api: str, **kwargs) -> None:
        self.calls.append(kwargs)


def make_status(
    live_status: int,
    *,
    title: str = "轻量标题",
    live_time: str | None = None,
    area_name: str | None = None,
    parent_area_name: str | None = None,
    cover_url: str | None = None,
) -> LiveStatus:
    return LiveStatus(
        mid="42",
        room_id=100,
        title=title,
        live_status=live_status,
        live_time=live_time,
        area_name=area_name,
        parent_area_name=parent_area_name,
        cover_url=cover_url,
    )


class LiveAlertTests(unittest.TestCase):
    def setUp(self) -> None:
        live_alert._mid_locks.clear()
        service_mute._MUTED_GROUPS.clear()

    def _run_transition(
        self,
        store: LiveStateStore,
        status: LiveStatus,
        now: float,
        subscriptions: list[live_alert.Subscription],
    ) -> None:
        asyncio.run(
            live_alert._handle_status(
                cast(live_alert.BiliClient, object()),
                "42",
                status,
                subscriptions,
                store,
                live_alert.RequestPacer(interval=0),
                now,
            )
        )

    def test_transition_queries_details_once_and_notifies_each_group(self) -> None:
        bot = FakeBot()
        detail_calls: list[int] = []

        async def details(_client: object, room_id: int) -> LiveStatus:
            detail_calls.append(room_id)
            return make_status(
                1,
                title="详细标题",
                live_time="2026-08-05 18:23:00",
                area_name="萌宅领域",
                parent_area_name="娱乐",
                cover_url="https://example.test/cover.jpg",
            )

        subscriptions = [
            live_alert.Subscription(group_id="1", subscribed_at=1),
            live_alert.Subscription(group_id="2", subscribed_at=1),
        ]
        group_config = {"enable": True, "mids": ["42"], "add_url": True}
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(live_alert, "get_live_room_info", new=details),
            patch.object(live_alert, "get_onebot_bot", return_value=cast(Bot, bot)),
            patch.object(live_alert, "_group_item", return_value=group_config),
            patch.object(live_alert, "_group_still_subscribes", return_value=True),
            patch.object(live_alert, "DRY_RUN", False),
        ):
            store = LiveStateStore(Path(directory))
            self._run_transition(store, make_status(0), 10, subscriptions)
            self._run_transition(store, make_status(1), 20, subscriptions)

            state = store.load("42")

        self.assertEqual(detail_calls, [100])
        self.assertEqual(len(bot.calls), 2)
        self.assertEqual(
            [segment.type for segment in bot.calls[0]["message"]],
            ["text", "text", "text", "text", "image", "text"],
        )
        self.assertEqual(
            bot.calls[0]["message"][4].data["file"],
            "https://example.test/cover.jpg",
        )
        assert state is not None
        assert state.active is not None
        self.assertEqual(state.active.session_id, "100:2026-08-05 18:23:00")
        self.assertEqual(state.active.cover_url, "https://example.test/cover.jpg")
        self.assertEqual(state.active.open_sent, ["1", "2"])

    def test_detail_failure_sends_basic_message_then_retries_without_duplicate(
        self,
    ) -> None:
        bot = FakeBot()
        detail_calls = 0

        async def details(_client: object, _room_id: int) -> LiveStatus:
            nonlocal detail_calls
            detail_calls += 1
            if detail_calls == 1:
                raise RuntimeError("temporary detail failure")
            return make_status(1, title="详细标题", live_time="2026-08-05 18:23:00")

        subscriptions = [live_alert.Subscription(group_id="1", subscribed_at=1)]
        group_config = {"enable": True, "mids": ["42"], "add_url": False}
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(live_alert, "get_live_room_info", new=details),
            patch.object(live_alert, "get_onebot_bot", return_value=cast(Bot, bot)),
            patch.object(live_alert, "_group_item", return_value=group_config),
            patch.object(live_alert, "_group_still_subscribes", return_value=True),
            patch.object(live_alert, "DRY_RUN", False),
        ):
            store = LiveStateStore(Path(directory))
            self._run_transition(store, make_status(0), 10, subscriptions)
            self._run_transition(store, make_status(1), 20, subscriptions)
            self._run_transition(store, make_status(1), 21, subscriptions)
            self._run_transition(store, make_status(1), 30, subscriptions)
            state = store.load("42")

        self.assertEqual(detail_calls, 2)
        self.assertEqual(len(bot.calls), 1)
        self.assertEqual(
            str(bot.calls[0]["message"]), "你关注的 UP 主正在直播～\n轻量标题"
        )
        assert state is not None
        assert state.active is not None
        self.assertEqual(state.active.live_time, "2026-08-05 18:23:00")
        self.assertIsNone(state.active.detail_retry_at)

    def test_close_delivery_stays_queued_until_a_bot_is_available(self) -> None:
        session = LiveSession(
            session_id="100:2026-08-05 18:23:00",
            room_id=100,
            opened_at=10,
            title="直播标题",
            live_time="2026-08-05 18:23:00",
            open_sent=["1"],
        )
        bot = FakeBot()
        group_config = {
            "enable": True,
            "mids": ["42"],
            "add_url": False,
            "notify_on_close": True,
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(live_alert, "_group_item", return_value=group_config),
            patch.object(live_alert, "_group_still_subscribes", return_value=True),
            patch.object(live_alert, "DRY_RUN", False),
        ):
            store = LiveStateStore(Path(directory))
            store.save("42", LiveState(last_status=1, active=session))
            with patch.object(live_alert, "get_onebot_bot", return_value=None):
                self._run_transition(store, make_status(0), 30, [])
            queued_state = store.load("42")
            assert queued_state is not None
            self.assertEqual(len(queued_state.closing), 1)

            with patch.object(
                live_alert, "get_onebot_bot", return_value=cast(Bot, bot)
            ):
                self._run_transition(store, make_status(0), 31, [])
            state = store.load("42")

        self.assertEqual(len(bot.calls), 1)
        self.assertIn("下播时间：", str(bot.calls[0]["message"]))
        assert state is not None
        self.assertEqual(state.closing, [])

    def test_muted_group_discards_live_notification(self) -> None:
        bot = FakeBot()
        session = LiveSession(
            session_id="100:1",
            room_id=100,
            opened_at=1,
            title="直播标题",
        )
        service_mute.mute_group("1")

        with patch.object(live_alert, "DRY_RUN", False):
            sent = asyncio.run(
                live_alert._send_open(cast(Bot, bot), "1", "42", session)
            )

        self.assertTrue(sent)
        self.assertEqual(bot.calls, [])

    def test_state_reads_the_legacy_single_closing_session(self) -> None:
        session = LiveSession(
            session_id="100:1",
            room_id=100,
            opened_at=1,
            title="标题",
        )
        state = LiveState.from_dict(
            {"last_status": 0, "active": None, "closing": session.to_dict()}
        )

        assert state is not None
        self.assertEqual([item.session_id for item in state.closing], ["100:1"])


if __name__ == "__main__":
    unittest.main()
