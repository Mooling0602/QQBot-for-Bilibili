"""Persistent state for live notification sessions."""

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item))


@dataclass
class LiveSession:
    """One observed live session and its group-level delivery state."""

    session_id: str
    room_id: int | None
    opened_at: float
    title: str
    live_time: str | None = None
    area_name: str | None = None
    parent_area_name: str | None = None
    detail_retry_at: float | None = None
    detail_retry_interval: float = 1.0
    open_targets: list[str] = field(default_factory=list)
    open_sent: list[str] = field(default_factory=list)
    close_targets: list[str] = field(default_factory=list)
    close_sent: list[str] = field(default_factory=list)
    closed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "room_id": self.room_id,
            "opened_at": self.opened_at,
            "title": self.title,
            "live_time": self.live_time,
            "area_name": self.area_name,
            "parent_area_name": self.parent_area_name,
            "detail_retry_at": self.detail_retry_at,
            "detail_retry_interval": self.detail_retry_interval,
            "open_targets": self.open_targets,
            "open_sent": self.open_sent,
            "close_targets": self.close_targets,
            "close_sent": self.close_sent,
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "LiveSession | None":
        if not isinstance(value, dict):
            return None
        session_id = _optional_str(value.get("session_id"))
        opened_at = _optional_float(value.get("opened_at"))
        if session_id is None or opened_at is None:
            return None
        retry_interval = _optional_float(value.get("detail_retry_interval")) or 1.0
        return cls(
            session_id=session_id,
            room_id=_optional_int(value.get("room_id")),
            opened_at=opened_at,
            title=_optional_str(value.get("title")) or "",
            live_time=_optional_str(value.get("live_time")),
            area_name=_optional_str(value.get("area_name")),
            parent_area_name=_optional_str(value.get("parent_area_name")),
            detail_retry_at=_optional_float(value.get("detail_retry_at")),
            detail_retry_interval=max(1.0, retry_interval),
            open_targets=_string_list(value.get("open_targets")),
            open_sent=_string_list(value.get("open_sent")),
            close_targets=_string_list(value.get("close_targets")),
            close_sent=_string_list(value.get("close_sent")),
            closed_at=_optional_float(value.get("closed_at")),
        )


@dataclass
class LiveState:
    """Last successful status and any active or closing session."""

    last_status: int
    active: LiveSession | None = None
    closing: list[LiveSession] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_status": self.last_status,
            "active": self.active.to_dict() if self.active else None,
            "closing": [session.to_dict() for session in self.closing],
        }

    @classmethod
    def from_dict(cls, value: object) -> "LiveState | None":
        if not isinstance(value, dict):
            return None
        last_status = _optional_int(value.get("last_status"))
        if last_status not in {0, 1, 2}:
            return None
        raw_closing = value.get("closing")
        if isinstance(raw_closing, list):
            closing = [
                session
                for session in (LiveSession.from_dict(item) for item in raw_closing)
                if session is not None
            ]
        else:
            legacy_session = LiveSession.from_dict(raw_closing)
            closing = [legacy_session] if legacy_session else []
        return cls(
            last_status=last_status,
            active=LiveSession.from_dict(value.get("active")),
            closing=closing,
        )


class LiveStateStore:
    """Atomic JSON state files, isolated from dynamic seen-state files."""

    def __init__(self, state_dir: Path):
        self._state_dir = state_dir

    def _path(self, mid: str) -> Path:
        return self._state_dir / f"live_{mid}.json"

    def load(self, mid: str) -> LiveState | None:
        path = self._path(mid)
        try:
            with open(path, encoding="utf-8") as file:
                return LiveState.from_dict(json.load(file))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return None

    def save(self, mid: str, state: LiveState) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        target = self._path(mid)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=self._state_dir
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(state.to_dict(), temporary, ensure_ascii=False)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, target)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
