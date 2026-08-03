"""状态检查命令（管理员专属）：@机器人 发送 /检查状态 时返回机器人运行状态。"""

import time
from datetime import datetime

from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot.rule import to_me

from qqbot.core.permissions import admin_only
from qqbot.core.version import get_version

START_TIME = time.time()

check_status = on_command(
    "检查状态",
    rule=to_me(),
    permission=admin_only(),
    priority=10,
    block=True,
)


def _format_start_time() -> str:
    dt = datetime.fromtimestamp(START_TIME)
    return f"{dt.year}.{dt.month}.{dt.day} {dt.hour:02d}:{dt.minute:02d}"


def _format_uptime() -> str:
    minutes = int(time.time() - START_TIME) // 60
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    parts.append(f"{minutes} 分钟")
    return " ".join(parts)


@check_status.handle()
async def handle_check_status(bot: Bot, event: Event) -> None:
    await check_status.finish(
        f"版本：v{get_version()}\n"
        f"最近启动时间：{_format_start_time()}\n"
        f"已运行：{_format_uptime()}\n"
        f"当前服务状态正常"
    )
