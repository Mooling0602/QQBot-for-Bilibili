import asyncio
import tempfile
import unittest
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
        self.assertEqual([segment.type for segment in message], ["text", "text", "image"])
        self.assertEqual(message[0].data["text"], "提示词")
        self.assertEqual(message[1].data["text"], "\n动态标题")

    def test_missing_screenshot_forces_dynamic_url(self) -> None:
        bot = FakeBot()
        config = {"enable": True, "mids": ["42"], "prompt": "提示词", "add_url": False}

        with (
            patch.object(dynamic_push, "_group_still_subscribes", return_value=True),
            patch.object(dynamic_push, "_group_item", return_value=config),
            patch.object(dynamic_push, "DRY_RUN", False),
        ):
            self.assertTrue(
                asyncio.run(
                    dynamic_push._send_to_group(cast(Bot, bot), "1", make_notice(), None)
                )
            )

        message = bot.calls[0]["message"]
        self.assertEqual([segment.type for segment in message], ["text", "text", "text"])
        self.assertEqual(message[2].data["text"], "\nhttps://t.bilibili.com/100")


if __name__ == "__main__":
    unittest.main()
