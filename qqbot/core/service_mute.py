"""In-memory, group-scoped message mute state."""

_MUTED_GROUPS: set[str] = set()


def mute_group(group_id: str | int) -> None:
    """Prevent this group from receiving messages until the bot is restarted."""
    _MUTED_GROUPS.add(str(group_id))


def resume_group(group_id: str | int) -> None:
    """Resume normal messages for one group."""
    _MUTED_GROUPS.discard(str(group_id))


def is_group_muted(group_id: str | int) -> bool:
    """Whether outgoing and command messages are muted for one group."""
    return str(group_id) in _MUTED_GROUPS
