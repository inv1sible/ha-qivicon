"""QIVICON switch entities."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import QiviconConfigEntry
from .const import NULL_STATES
from .entity import QiviconEntity, item_device_id, item_is_visible, item_is_writable


async def async_setup_entry(
    hass, entry: QiviconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities = []
    for item in coordinator.data.items:
        if item.get("type") != "Switch":
            continue
        if not item_is_writable(item) or not item_is_visible(
            item, coordinator.data.devices, coordinator.data.items
        ):
            continue
        entities.append(
            QiviconSwitch(
                coordinator,
                item["name"],
                item_device_id(item, coordinator.data.devices, coordinator.data.items),
            )
        )
    async_add_entities(entities)


class QiviconSwitch(QiviconEntity, SwitchEntity):
    @property
    def name(self) -> str:
        if (
            (self.device or {}).get("detail", {}).get("model") == "HMIP-PSM"
            and "capability:switchable" in (self.item.get("tags") or [])
        ):
            return "Power"
        return self.item.get("label") or self.item_name

    @property
    def is_on(self) -> bool | None:
        state = self.item.get("state")
        if state in NULL_STATES:
            return None
        return str(state).upper() == "ON"

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.client.send_item_command(self.item_name, "ON")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.send_item_command(self.item_name, "OFF")
        await self.coordinator.async_request_refresh()
