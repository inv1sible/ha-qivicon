"""QIVICON data coordinator."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import logging
from typing import Any, Awaitable, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import QiviconClient, QiviconError, QiviconSnapshot
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class QiviconCoordinator(DataUpdateCoordinator[QiviconSnapshot]):
    """Fetch shared QIVICON data when the Home Base publishes an event."""

    def __init__(self, hass: HomeAssistant, client: QiviconClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
        )
        self.client = client
        self.event_capture = QiviconEventCapture(client)
        self.event_listener = QiviconEventListener(client, self._async_event_refresh)
        self._last_snapshot_refresh_at: str | None = None
        self._last_snapshot_refresh_trigger = "startup"
        self._last_snapshot_error: str | None = None

    async def async_start_event_listener(self) -> None:
        """Start listening after Home Assistant has the initial snapshot."""
        await self.event_listener.start()

    async def async_stop_event_listener(self) -> None:
        """Stop the long-polling event listener."""
        await self.event_listener.stop()

    async def _async_event_refresh(self, trigger: str) -> None:
        """Refresh one full snapshot for an event or recovered subscription."""
        self._last_snapshot_refresh_trigger = trigger
        await self.async_request_refresh()

    async def _async_update_data(self) -> QiviconSnapshot:
        try:
            snapshot = await self.client.get_snapshot()
        except QiviconError as err:
            self._last_snapshot_error = str(err)
            raise UpdateFailed(str(err)) from err
        self._last_snapshot_refresh_at = datetime.now(timezone.utc).isoformat()
        self._last_snapshot_error = None
        return snapshot

    def diagnostics(self) -> dict[str, Any]:
        """Return transport diagnostics without creating Home Assistant entities."""
        return {
            "polling": {"enabled": False},
            "last_snapshot_refresh_at": self._last_snapshot_refresh_at,
            "last_snapshot_refresh_trigger": self._last_snapshot_refresh_trigger,
            "last_snapshot_error": self._last_snapshot_error,
            "event_listener": self.event_listener.diagnostics(),
        }


EVENT_TOPICS = [
    "smarthome/*",
    "com/*",
    "org/*",
    "openhab/*",
    "dect/*",
    "homematic/*",
    "hmip/*",
    "zigbee/*",
]
_SECRET_KEYS = ("password", "token", "cookie", "authorization", "secret")
EVENT_REFRESH_DEBOUNCE_SECONDS = 1
EVENT_RECONNECT_DELAY_SECONDS = 5


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


class QiviconEventListener:
    """Keep a QIVICON remote-event subscription alive for live updates."""

    def __init__(
        self,
        client: QiviconClient,
        refresh_callback: Callable[[str], Awaitable[None]],
    ) -> None:
        self.client = client
        self.refresh_callback = refresh_callback
        self.task: asyncio.Task[None] | None = None
        self.refresh_task: asyncio.Task[None] | None = None
        self.subscription_id: Any = None
        self.started_at: str | None = None
        self.connected_at: str | None = None
        self.disconnected_at: str | None = None
        self.last_event_at: str | None = None
        self.last_refresh_requested_at: str | None = None
        self.last_error: str | None = None
        self.last_error_at: str | None = None
        self.event_count = 0
        self.reconnect_count = 0
        self._has_connected = False

    @property
    def active(self) -> bool:
        return self.task is not None and not self.task.done()

    async def start(self) -> None:
        """Start one subscription task when it is not already running."""
        if self.active:
            return
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the listener and any queued event refresh."""
        refresh_task = self.refresh_task
        if refresh_task is not None and not refresh_task.done():
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass
        task = self.task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            subscription_id: Any = None
            try:
                topics = [{"topic": topic} for topic in EVENT_TOPICS]
                subscription_id = await self.client.rpc_call("RE/subscribe", [topics])
                self.subscription_id = subscription_id
                self.connected_at = datetime.now(timezone.utc).isoformat()
                self.disconnected_at = None
                self.last_error = None

                if self._has_connected:
                    await self._request_refresh("reconnect")
                self._has_connected = True

                sequence = 0
                while True:
                    batch = await self.client.rpc_call(
                        "RE/longPoll", [subscription_id, 10, sequence]
                    )
                    if not batch:
                        continue
                    for event in batch:
                        properties = event.get("properties") or {}
                        event_sequence = properties.get(
                            "com.qivicon.services.remote.event.sequence.number"
                        )
                        if isinstance(event_sequence, int):
                            sequence = max(sequence, event_sequence)
                        self.event_count += 1
                    self.last_event_at = datetime.now(timezone.utc).isoformat()
                    self._schedule_event_refresh()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self.last_error = str(err)
                self.last_error_at = datetime.now(timezone.utc).isoformat()
                self.disconnected_at = self.last_error_at
                self.reconnect_count += 1
                _LOGGER.warning("QIVICON event subscription ended: %s", err)
            finally:
                self.subscription_id = None
                if subscription_id is not None:
                    try:
                        await self.client.rpc_call("RE/unsubscribe", [subscription_id])
                    except QiviconError:
                        pass
            await asyncio.sleep(EVENT_RECONNECT_DELAY_SECONDS)

    def _schedule_event_refresh(self) -> None:
        if self.refresh_task is None or self.refresh_task.done():
            self.refresh_task = asyncio.create_task(self._debounced_event_refresh())

    async def _debounced_event_refresh(self) -> None:
        try:
            await asyncio.sleep(EVENT_REFRESH_DEBOUNCE_SECONDS)
            await self._request_refresh("event")
        except asyncio.CancelledError:
            raise
        except Exception as err:  # Keep listening when a snapshot refresh fails.
            self.last_error = str(err)
            self.last_error_at = datetime.now(timezone.utc).isoformat()
            _LOGGER.warning("QIVICON event-triggered refresh failed: %s", err)

    async def _request_refresh(self, trigger: str) -> None:
        self.last_refresh_requested_at = datetime.now(timezone.utc).isoformat()
        await self.refresh_callback(trigger)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "subscribed": self.subscription_id is not None,
            "started_at": self.started_at,
            "connected_at": self.connected_at,
            "disconnected_at": self.disconnected_at,
            "last_event_at": self.last_event_at,
            "last_refresh_requested_at": self.last_refresh_requested_at,
            "event_count": self.event_count,
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "topics": EVENT_TOPICS,
        }


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
