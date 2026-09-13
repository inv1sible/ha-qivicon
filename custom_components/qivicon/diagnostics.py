"""Diagnostics for QIVICON."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import QiviconConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: QiviconConfigEntry
) -> dict[str, Any]:
    """Return the full non-secret inventory for troubleshooting new capabilities."""
    snapshot = entry.runtime_data.data
    return {
        "host": entry.runtime_data.client.host,
        "system": snapshot.system,
        "devices": snapshot.devices,
        "items": snapshot.items,
        "rooms": snapshot.rooms,
    }
