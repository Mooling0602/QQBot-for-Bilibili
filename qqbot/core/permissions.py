"""权限模块：管理员账号判断与命令权限规则。

管理员来源（配置在 qqbot/config.yml 的 permissions 节）：
1. admin_users 显式配置的账号
2. auto_admin=true 时：群聊内的群主/管理员自动视为管理员

无权限拒绝行为见 docs/qqbot-command-spec.md 第 4 节：
- 静默：permission=admin_only()，匹配器不匹配，不做响应
- 提示：handler 开头调用 ensure_admin()，无权限时回复提示并中断
"""

from nonebot.adapters import Event
from nonebot.permission import Permission

from qqbot.core.config import CONFIG

DENY_MESSAGE = "权限不足：该命令仅管理员可用"

_permissions_cfg = CONFIG.get("permissions", {})

# 自动识别：群聊管理员/群主自动视为管理员
AUTO_ADMIN: bool = bool(_permissions_cfg.get("auto_admin", False))

ADMIN_USERS: list[int] = list(_permissions_cfg.get("admin_users", []))

_ADMIN_ROLES = ("owner", "admin")


def is_admin(user_id: str | int, role: str | None = None) -> bool:
    """判断用户是否为管理员。

    role 为群内角色（"owner"/"admin"/"member"），仅 AUTO_ADMIN 开启时参与判断。
    """
    if str(user_id) in {str(u) for u in ADMIN_USERS}:
        return True
    return bool(AUTO_ADMIN and role in _ADMIN_ROLES)


def _event_role(event: Event) -> str | None:
    """从事件中提取群内角色（非群聊事件返回 None）。"""
    sender = getattr(event, "sender", None)
    return getattr(sender, "role", None) if sender else None


def _check_admin(event: Event) -> bool:
    return is_admin(event.get_user_id(), _event_role(event))


def is_admin_event(event: Event) -> bool:
    """Return whether an event sender is a configured administrator."""
    return _check_admin(event)


def admin_only() -> Permission:
    """管理员专属命令权限规则（静默拒绝）。"""

    return Permission(_check_admin)


async def ensure_admin(event: Event, matcher) -> None:
    """handler 内权限检查：无权限时回复提示并中断命令处理。"""

    if not _check_admin(event):
        await matcher.finish(DENY_MESSAGE)
