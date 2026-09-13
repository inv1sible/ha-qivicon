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


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the escape-hatch service for raw QIVICON capabilities."""

    async def async_send_item_command(call: ServiceCall) -> None:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state.name == "LOADED"
        ]
        requested_entry = call.data.get("entry_id")
        if requested_entry:
            entries = [entry for entry in entries if entry.entry_id == requested_entry]
        if not entries:
            raise ValueError("No matching loaded QIVICON config entry")
        if len(entries) > 1:
            raise ValueError("entry_id is required when multiple QIVICON hubs are loaded")
        coordinator: QiviconCoordinator = entries[0].runtime_data
        await coordinator.client.send_item_command(
            call.data["item"], call.data["command"]
        )
        await coordinator.async_request_refresh()

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
        await entry.runtime_data.client.close()
    return unloaded
