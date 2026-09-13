"""QIVICON sensor entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature
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
        tags = item.get("tags") or []
        item_type = item.get("type") or ""
        if not item_type.startswith(("Number", "String", "DateTime")):
            continue
        if item_is_writable(item):
            continue
        entities.append(
            QiviconSensor(
                coordinator,
                item["name"],
                item_device_id(item, coordinator.data.devices, coordinator.data.items),
            )
        )
    async_add_entities(entities)


class QiviconSensor(QiviconEntity, SensorEntity):
    @property
    def name(self) -> str:
        return self.item.get("label") or self.item_name

    @property
    def native_value(self) -> Any:
        state = self.item.get("state")
        if state in NULL_STATES:
            return None
        try:
            return float(str(state).split()[0])
        except (TypeError, ValueError):
            return state

    @property
    def device_class(self):
        category = (self.item.get("category") or "").lower()
        if category == "temperature":
            return SensorDeviceClass.TEMPERATURE
        if category == "humidity":
            return SensorDeviceClass.HUMIDITY
        if category == "battery":
            return SensorDeviceClass.BATTERY
        if category == "power":
            return SensorDeviceClass.POWER
        if category == "energy":
            return SensorDeviceClass.ENERGY
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        pattern = (self.item.get("stateDescription") or {}).get("pattern", "")
        if "°C" in pattern:
            return UnitOfTemperature.CELSIUS
        parts = pattern.split(" ", 1)
        return parts[1] if len(parts) == 2 and "%" in parts[0] else None
