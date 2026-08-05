import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from unittest.mock import patch

import nonebot
from nonebot.adapters.onebot.v11 import Bot

nonebot.init()

from qqbot.plugins import dynamic_push


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def call_api(self, _api: str, **kwargs) -> None:
        self.calls.append(kwargs)


class FakeBiliClient:
    def __init__(self, has_sessdata: bool) -> None:
        self.has_sessdata = has_sessdata


class FakeFeedAllWatcher:
    def __init__(self, items: dict[str, list[dict]]) -> None:
        self.items = items
        self.calls: list[list[str]] = []

    async def fetch_unseen(self, mids: list[str]) -> dict[str, list[dict]]:
        self.calls.append(mids)
        return {mid: self.items[mid] for mid in mids if mid in self.items}


class FakeSpaceWatcher:
    def __init__(self, items: dict[str, list[dict]]) -> None:
        self.items = items
        self.calls: list[str] = []

    async def fetch_unseen(self, mid: str) -> list[dict]:
        self.calls.append(mid)
        return self.items.get(mid, [])


def make_notice() -> dynamic_push.DynamicNotice:
    return dynamic_push.DynamicNotice(
        dynamic_id="100",
        mid="42",
        published_at=200.0,
        title="动态标题",
    )


class DynamicPushTests(unittest.TestCase):
    def setUp(self) -> None:
        dynamic_push._screenshot_cache.clear()
        dynamic_push._screenshot_tasks.clear()
        dynamic_push._following_status.clear()

    def test_screenshot_cache_merges_same_dynamic_requests(self) -> None:
        calls = 0

        async def fake_fetch(_dynamic_id: str, remote_url: str | None = None) -> bytes:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return b"png"

        async def run() -> None:
            first, second = await asyncio.gather(
                dynamic_push._get_screenshot("100"),
                dynamic_push._get_screenshot("100"),
            )
            third = await dynamic_push._get_screenshot("100")
            self.assertEqual((first, second, third), (b"png", b"png", b"png"))

        with patch.object(dynamic_push, "fetch_dynamic_screenshot", new=fake_fetch):
            asyncio.run(run())
        self.assertEqual(calls, 1)

    def test_collect_watch_backfills_legacy_subscription_time(self) -> None:
        data = {"dynamic_push": {"enable": True, "mids": ["42"]}}
        saved: list[dict] = []

        with tempfile.TemporaryDirectory() as directory:
            group_dir = Path(directory) / "1"
            group_dir.mkdir()
            with (
                patch.object(dynamic_push, "GROUP_CONFIG_ROOT", Path(directory)),
                patch.object(dynamic_push, "load_group_config", return_value=data),
                patch.object(
                    dynamic_push,
                    "save_group_config",
                    side_effect=lambda _group_id, value: saved.append(value),
                ),
            ):
                watch = dynamic_push._collect_watch()

        self.assertEqual(watch["42"][0].group_id, "1")
        self.assertGreater(watch["42"][0].subscribed_at, 0)
        self.assertEqual(len(saved), 1)
        self.assertIn("42", saved[0]["dynamic_push"]["mid_subscribed_at"])

    def test_screenshot_success_respects_add_url_and_includes_title(self) -> None:
        bot = FakeBot()
        config = {"enable": True, "mids": ["42"], "prompt": "提示词", "add_url": False}

        with (
            patch.object(dynamic_push, "_group_still_subscribes", return_value=True),
            patch.object(dynamic_push, "_group_item", return_value=config),
            patch.object(dynamic_push, "DRY_RUN", False),
        ):
            self.assertTrue(
                asyncio.run(
                    dynamic_push._send_to_group(
                        cast(Bot, bot), "1", make_notice(), b"png"
                    )
                )
            )

        message = bot.calls[0]["message"]
        self.assertEqual(
            [segment.type for segment in message], ["text", "text", "image"]
        )
        self.assertEqual(message[0].data["text"], "提示词")
        self.assertEqual(message[1].data["text"], "\n动态标题")

    def test_missing_screenshot_forces_dynamic_url(self) -> None:
        bot = FakeBot()
        config = {"enable": True, "mids": ["42"], "prompt": "提示词", "add_url": False}

        with (
            patch.object(dynamic_push, "_group_still_subscribes", return_value=True),
            patch.object(dynamic_push, "_group_item", return_value=config),
            patch.object(dynamic_push, "DRY_RUN", False),
            patch.object(
                dynamic_push, "_format_published_at", return_value="今天 18:23"
            ),
        ):
            self.assertTrue(
                asyncio.run(
                    dynamic_push._send_to_group(
                        cast(Bot, bot), "1", make_notice(), None
                    )
                )
            )

        message = bot.calls[0]["message"]
        self.assertEqual(
            [segment.type for segment in message], ["text", "text", "text", "text"]
        )
        self.assertEqual(message[2].data["text"], "\n发布时间：今天 18:23")
        self.assertEqual(message[3].data["text"], "\nhttps://t.bilibili.com/100")

    def test_format_published_at_uses_relative_days_and_minutes(self) -> None:
        now = datetime(2026, 8, 5, 18, 30, tzinfo=timezone.utc)

        def timestamp(days_ago: int) -> float:
            return (now - timedelta(days=days_ago, minutes=7)).timestamp()

        with patch.object(dynamic_push, "LOCAL_TZ", timezone.utc):
            self.assertEqual(
                dynamic_push._format_published_at(timestamp(0), now=now), "今天 18:23"
            )
            self.assertEqual(
                dynamic_push._format_published_at(timestamp(1), now=now), "昨天 18:23"
            )
            self.assertEqual(
                dynamic_push._format_published_at(timestamp(2), now=now), "前天 18:23"
            )
            self.assertEqual(
                dynamic_push._format_published_at(timestamp(3), now=now),
                "2026年08月02日 18:23",
            )

    def test_missing_screenshot_still_sends_url_when_time_formatting_fails(
        self,
    ) -> None:
        bot = FakeBot()
        config = {"enable": True, "mids": ["42"], "prompt": "提示词", "add_url": False}

        with (
            patch.object(dynamic_push, "_group_still_subscribes", return_value=True),
            patch.object(dynamic_push, "_group_item", return_value=config),
            patch.object(dynamic_push, "DRY_RUN", False),
            patch.object(dynamic_push, "_format_published_at", return_value=None),
        ):
            self.assertTrue(
                asyncio.run(
                    dynamic_push._send_to_group(
                        cast(Bot, bot), "1", make_notice(), None
                    )
                )
            )

        message = bot.calls[0]["message"]
        self.assertEqual(
            [segment.type for segment in message], ["text", "text", "text"]
        )
        self.assertEqual(message[2].data["text"], "\nhttps://t.bilibili.com/100")

    def test_source_selection_without_sessdata_uses_feed_space(self) -> None:
        sources = asyncio.run(
            dynamic_push._resolve_dynamic_sources(
                cast(dynamic_push.BiliClient, FakeBiliClient(False)),
                ["42", "43", "42"],
                now=100.0,
            )
        )

        self.assertEqual(sources, ([], ["42", "43"]))

    def test_source_selection_uses_feed_all_after_manual_follow(self) -> None:
        calls: list[str] = []
        follows = False

        async def fake_is_following(_client: object, mid: str) -> bool:
            calls.append(mid)
            return follows

        client = cast(dynamic_push.BiliClient, FakeBiliClient(True))
        with patch.object(dynamic_push, "is_following", new=fake_is_following):
            first = asyncio.run(
                dynamic_push._resolve_dynamic_sources(client, ["42"], now=100.0)
            )
            cached = asyncio.run(
                dynamic_push._resolve_dynamic_sources(client, ["42"], now=200.0)
            )
            follows = True
            refreshed = asyncio.run(
                dynamic_push._resolve_dynamic_sources(
                    client,
                    ["42"],
                    now=100.0 + dynamic_push.FOLLOWING_RECHECK_SEC,
                )
            )

        self.assertEqual(first, ([], ["42"]))
        self.assertEqual(cached, ([], ["42"]))
        self.assertEqual(refreshed, (["42"], []))
        self.assertEqual(calls, ["42", "42"])

    def test_candidate_fetch_uses_the_selected_source_once(self) -> None:
        feed_all = FakeFeedAllWatcher({"42": [{"id_str": "all"}]})
        feed_space = FakeSpaceWatcher({"43": [{"id_str": "space"}]})

        candidates = asyncio.run(
            dynamic_push._fetch_candidates(
                cast(dynamic_push.FeedAllWatcher, feed_all),
                cast(dynamic_push.DynamicWatcher, feed_space),
                ["42"],
                ["43"],
            )
        )

        self.assertEqual(
            candidates,
            {"42": [{"id_str": "all"}], "43": [{"id_str": "space"}]},
        )
        self.assertEqual(feed_all.calls, [["42"]])
        self.assertEqual(feed_space.calls, ["43"])


if __name__ == "__main__":
    unittest.main()
