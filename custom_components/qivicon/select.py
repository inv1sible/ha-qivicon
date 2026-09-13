"""Writable enumerated QIVICON parameters."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import QiviconConfigEntry
from .const import NULL_STATES
from .entity import QiviconEntity, item_device_id, item_is_writable


async def async_setup_entry(
    hass, entry: QiviconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities = []
    for item in coordinator.data.items:
        options = (item.get("stateDescription") or {}).get("options") or []
        values = [str(option.get("value")) for option in options if option.get("value")]
        if item.get("type") != "String" or not item_is_writable(item) or not values:
            continue
        entities.append(
            QiviconSelect(
                coordinator,
                item["name"],
                item_device_id(item, coordinator.data.devices, coordinator.data.items),
            )
        )
    async_add_entities(entities)


class QiviconSelect(QiviconEntity, SelectEntity):
    @property
    def name(self) -> str:
        return self.item.get("label") or self.item_name

    @property
    def options(self) -> list[str]:
        raw = (self.item.get("stateDescription") or {}).get("options") or []
        return [str(option.get("value")) for option in raw if option.get("value")]

    @property
    def current_option(self) -> str | None:
        state = self.item.get("state")
        return None if state in NULL_STATES else str(state)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.send_item_command(self.item_name, option)
        await self.coordinator.async_request_refresh()
