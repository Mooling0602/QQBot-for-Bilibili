"""OneBot connection selection shared by notification plugins."""

from typing import cast

from nonebot import get_bots, logger
from nonebot.adapters.onebot.v11 import Bot


def get_onebot_bot() -> Bot | None:
    """Return one connected OneBot v11 bot, if available."""
    try:
        for bot in get_bots().values():
            if bot.type == "OneBot V11" or "OneBot" in str(bot.type):
                return cast(Bot, bot)
    except Exception as error:  # noqa: BLE001
        logger.warning(f"获取 OneBot 连接状态失败: {error}")
    return None
