"""命令提示：@机器人 发送无斜杠的命令名（全文匹配、无参数）时，
提示用户补充斜杠开头。

不提示的情况：
- 消息以 / 开头（正常命令，交给命令匹配器）
- 消息带自定义参数（如"查询 username"全文不等于命令名"查询"）
"""

from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot.rule import to_me

from qqbot.core.commands import get_command_names

cmd_hint = on_message(rule=to_me(), priority=1, block=False)

HINT_MESSAGE = "若要使用命令，请补充斜杠（/）开头。"


@cmd_hint.handle()
async def handle_cmd_hint(bot: Bot, event: Event) -> None:
    text = event.get_plaintext().strip()
    if not text or text.startswith("/"):
        return
    if text in get_command_names():
        await cmd_hint.finish(HINT_MESSAGE)
