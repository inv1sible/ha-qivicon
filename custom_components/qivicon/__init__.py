"""QIVICON integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from .api import QiviconClient
from .const import DOMAIN, PLATFORMS
from .coordinator import QiviconCoordinator

type QiviconConfigEntry = ConfigEntry[QiviconCoordinator]

SERVICE_SEND_ITEM_COMMAND = "send_item_command"
SERVICE_START_EVENT_CAPTURE = "start_event_capture"
SERVICE_STOP_EVENT_CAPTURE = "stop_event_capture"


def _loaded_coordinator(hass: HomeAssistant, entry_id: str | None) -> QiviconCoordinator:
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state.name == "LOADED"
    ]
    if entry_id:
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    if not entries:
        raise ValueError("No matching loaded QIVICON config entry")
    if len(entries) > 1:
        raise ValueError("entry_id is required when multiple QIVICON hubs are loaded")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the escape-hatch service for raw QIVICON capabilities."""

    async def async_send_item_command(call: ServiceCall) -> None:
        coordinator = _loaded_coordinator(hass, call.data.get("entry_id"))
        await coordinator.client.send_item_command(
            call.data["item"], call.data["command"]
        )
        await coordinator.async_request_refresh()

    async def async_start_event_capture(call: ServiceCall) -> None:
        coordinator = _loaded_coordinator(hass, call.data.get("entry_id"))
        await coordinator.event_capture.start(call.data["duration"])

    async def async_stop_event_capture(call: ServiceCall) -> None:
        coordinator = _loaded_coordinator(hass, call.data.get("entry_id"))
        await coordinator.event_capture.stop()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_ITEM_COMMAND,
        async_send_item_command,
        schema=vol.Schema(
            {
                vol.Required("item"): str,
                vol.Required("command"): str,
                vol.Optional("entry_id"): str,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_EVENT_CAPTURE,
        async_start_event_capture,
        schema=vol.Schema(
            {
                vol.Optional("duration", default=120): vol.All(
                    vol.Coerce(int), vol.Range(min=10, max=600)
                ),
                vol.Optional("entry_id"): str,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_EVENT_CAPTURE,
        async_stop_event_capture,
        schema=vol.Schema({vol.Optional("entry_id"): str}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: QiviconConfigEntry) -> bool:
    client = QiviconClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PASSWORD],
        verify_ssl=False,
    )
    coordinator = QiviconCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"hub_{client.host}")},
        name=coordinator.data.system.get("label") or "QIVICON Home Base",
        manufacturer="Deutsche Telekom AG",
        model="QIVICON Home Base 2",
        configuration_url=client.base_url,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: QiviconConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.event_capture.stop()
        await entry.runtime_data.client.close()
    return unloaded
