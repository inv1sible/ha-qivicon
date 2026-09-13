"""Writable text and raw color QIVICON parameters."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
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
        options = (item.get("stateDescription") or {}).get("options") or []
        if item.get("type") != "String":
            continue
        if (
            not item_is_writable(item)
            or not item_is_visible(item, coordinator.data.devices, coordinator.data.items)
            or options
        ):
            continue
        entities.append(
            QiviconText(
                coordinator,
                item["name"],
                item_device_id(item, coordinator.data.devices, coordinator.data.items),
            )
        )
    async_add_entities(entities)


class QiviconText(QiviconEntity, TextEntity):
    @property
    def name(self) -> str:
        return self.item.get("label") or self.item_name

    @property
    def native_value(self) -> str | None:
        state = self.item.get("state")
        return None if state in NULL_STATES else str(state)

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.client.send_item_command(self.item_name, value)
        await self.coordinator.async_request_refresh()
