"""Group-scoped, in-memory service mute controls."""

from nonebot import logger, on_message
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule, to_me

from qqbot.core.group_config import get_group_id
from qqbot.core.permissions import is_admin_event
from qqbot.core.service_mute import is_group_muted, mute_group, resume_group

_MUTE_TEXTS = {"禁言", "/禁言"}
_RESUME_TEXT = "/恢复服务"


def _is_control_message(event: Event) -> bool:
    text = event.get_plaintext().strip()
    return get_group_id(event) is not None and text in _MUTE_TEXTS | {_RESUME_TEXT}


def _is_muted_group_message(event: Event) -> bool:
    group_id = get_group_id(event)
    return group_id is not None and is_group_muted(group_id)


service_control = on_message(
    rule=to_me() & Rule(_is_control_message), priority=-2, block=True
)
muted_group_guard = on_message(
    rule=Rule(_is_muted_group_message), priority=-1, block=True
)


@service_control.handle()
async def handle_service_control(bot: Bot, event: Event) -> None:
    group_id = get_group_id(event)
    if group_id is None or not is_admin_event(event):
        await service_control.finish()

    text = event.get_plaintext().strip()
    if text in _MUTE_TEXTS:
        mute_group(group_id)
        logger.warning(f"群 {group_id} 已被管理员静默，重启或 /恢复服务 后恢复")
        await service_control.finish()

    resume_group(group_id)
    logger.info(f"群 {group_id} 已恢复机器人消息服务")
    await service_control.finish("服务已恢复")


@muted_group_guard.handle()
async def handle_muted_group_guard(bot: Bot, event: Event) -> None:
    """Absorb every non-control message from a muted group without replying."""
    await muted_group_guard.finish()
