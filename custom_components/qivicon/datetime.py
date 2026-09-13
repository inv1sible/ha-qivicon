"""Writable QIVICON date/time parameters."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import QiviconConfigEntry
from .const import NULL_STATES
from .entity import QiviconEntity, item_device_id, item_is_visible, item_is_writable


async def async_setup_entry(
    hass, entry: QiviconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        QiviconDateTime(
            coordinator,
            item["name"],
            item_device_id(item, coordinator.data.devices, coordinator.data.items),
        )
        for item in coordinator.data.items
        if item.get("type") == "DateTime"
        and item_is_writable(item)
        and item_is_visible(item, coordinator.data.devices, coordinator.data.items)
    )


class QiviconDateTime(QiviconEntity, DateTimeEntity):
    @property
    def name(self) -> str:
        return self.item.get("label") or self.item_name

    @property
    def native_value(self) -> datetime | None:
        state = self.item.get("state")
        if state in NULL_STATES:
            return None
        try:
            return datetime.fromisoformat(str(state).replace("Z", "+00:00"))
        except ValueError:
            return None

    async def async_set_value(self, value: datetime) -> None:
        await self.coordinator.client.send_item_command(
            self.item_name, value.isoformat()
        )
        await self.coordinator.async_request_refresh()
