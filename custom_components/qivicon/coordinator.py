"""QIVICON data coordinator."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import QiviconClient, QiviconError, QiviconSnapshot
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class QiviconCoordinator(DataUpdateCoordinator[QiviconSnapshot]):
    """Fetch shared QIVICON data."""

    def __init__(self, hass: HomeAssistant, client: QiviconClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.event_capture = QiviconEventCapture(client)

    async def _async_update_data(self) -> QiviconSnapshot:
        try:
            return await self.client.get_snapshot()
        except QiviconError as err:
            raise UpdateFailed(str(err)) from err


EVENT_TOPICS = ["smarthome/*", "com/*", "org/*", "openhab/*", "dect/*"]
_SECRET_KEYS = ("password", "token", "cookie", "authorization", "secret")


def _redact(value: Any) -> Any:
    """Remove credentials if an unexpected event happens to contain them."""
    if isinstance(value, dict):
        return {
            key: "**REDACTED**" if any(part in key.lower() for part in _SECRET_KEYS)
            else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class QiviconEventCapture:
    """Keep a bounded diagnostic capture of QIVICON remote events."""

    def __init__(self, client: QiviconClient) -> None:
        self.client = client
        self.events: deque[dict[str, Any]] = deque(maxlen=500)
        self.task: asyncio.Task | None = None
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.duration = 0
        self.error: str | None = None
        self.subscription_id: Any = None

    @property
    def active(self) -> bool:
        return self.task is not None and not self.task.done()

    async def start(self, duration: int) -> None:
        await self.stop()
        self.events.clear()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.finished_at = None
        self.duration = duration
        self.error = None
        self.task = asyncio.create_task(self._capture(duration))

    async def stop(self) -> None:
        task = self.task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _capture(self, duration: int) -> None:
        sequence = 0
        deadline = asyncio.get_running_loop().time() + duration
        try:
            topics = [{"topic": topic} for topic in EVENT_TOPICS]
            self.subscription_id = await self.client.rpc_call("RE/subscribe", [topics])
            while (remaining := deadline - asyncio.get_running_loop().time()) > 0:
                timeout = max(1, min(10, int(remaining)))
                batch = await self.client.rpc_call(
                    "RE/longPoll", [self.subscription_id, timeout, sequence]
                )
                for event in batch or []:
                    properties = event.get("properties") or {}
                    event_sequence = properties.get(
                        "com.qivicon.services.remote.event.sequence.number"
                    )
                    if isinstance(event_sequence, int):
                        sequence = max(sequence, event_sequence)
                    self.events.append({
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                        "event": _redact(event),
                    })
        except asyncio.CancelledError:
            raise
        except QiviconError as err:
            self.error = str(err)
        finally:
            subscription_id = self.subscription_id
            self.subscription_id = None
            if subscription_id is not None:
                try:
                    await self.client.rpc_call("RE/unsubscribe", [subscription_id])
                except QiviconError:
                    pass
            self.finished_at = datetime.now(timezone.utc).isoformat()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "requested_duration_seconds": self.duration,
            "topics": EVENT_TOPICS,
            "event_count": len(self.events),
            "error": self.error,
            "events": list(self.events),
        }
