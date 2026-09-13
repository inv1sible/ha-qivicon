"""Writable numeric QIVICON parameters."""

from __future__ import annotations

import re

from homeassistant.components.number import NumberEntity
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
        item_type = item.get("type") or ""
        tags = item.get("tags") or []
        is_temperature = "property:temperature" in tags
        # All writable Dimmer items are exposed by the light platform.
        if (
            not item_is_writable(item)
            or not item_is_visible(item, coordinator.data.devices, coordinator.data.items)
            or is_temperature
            or item_type == "Dimmer"
        ):
            continue
        if not item_type.startswith("Number"):
            continue
        entities.append(
            QiviconNumber(
                coordinator,
                item["name"],
                item_device_id(item, coordinator.data.devices, coordinator.data.items),
            )
        )
    async_add_entities(entities)


def _number(value) -> float | None:
    if value in NULL_STATES:
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(value))
    return float(match.group(0).replace(",", ".")) if match else None


class QiviconNumber(QiviconEntity, NumberEntity):
    @property
    def name(self) -> str:
        return self.item.get("label") or self.item_name

    @property
    def native_value(self) -> float | None:
        return _number(self.item.get("state"))

    @property
    def native_min_value(self) -> float:
        return float((self.item.get("stateDescription") or {}).get("minimum", 0))

    @property
    def native_max_value(self) -> float:
        return float((self.item.get("stateDescription") or {}).get("maximum", 100))

    @property
    def native_step(self) -> float:
        return float((self.item.get("stateDescription") or {}).get("step", 1))

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.send_item_command(self.item_name, f"{value:g}")
        await self.coordinator.async_request_refresh()
