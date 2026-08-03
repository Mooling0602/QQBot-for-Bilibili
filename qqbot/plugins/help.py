"""帮助命令：/帮助

- 普通群成员（@不@均可）：显示公开用法
- 管理员 @机器人：显示公开用法 + 管理用法
"""

from nonebot import on_command
from nonebot.adapters import Bot, Event

from qqbot.core.permissions import is_admin
from qqbot.core.version import get_version

PUBLIC_HELP = f"""\
【测试1号机】在线 ✅（v{get_version()}）

公开命令：
/帮助 - 显示本帮助"""

ADMIN_HELP = """\
—— 管理命令 ——
/检查状态 - 查看机器人在线状态（需 @机器人）
/群配置 - 查看/修改本群配置（/群配置 设置 <键> <值>）"""

help_cmd = on_command("帮助", priority=1, block=True)


@help_cmd.handle()
async def handle_help(bot: Bot, event: Event) -> None:
    mentioned = getattr(event, "to_me", False)
    if is_admin(event.get_user_id()) and mentioned:
        await help_cmd.finish(ADMIN_HELP)
    else:
        await help_cmd.finish(PUBLIC_HELP)
