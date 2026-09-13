"""QIVICON binary sensor entities."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
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
        if item.get("type") not in ("Switch", "Contact"):
            continue
        if item_is_writable(item) or not item_is_visible(
            item, coordinator.data.devices, coordinator.data.items
        ):
            continue
        entities.append(
            QiviconBinarySensor(
                coordinator,
                item["name"],
                item_device_id(item, coordinator.data.devices, coordinator.data.items),
            )
        )
    async_add_entities(entities)


class QiviconBinarySensor(QiviconEntity, BinarySensorEntity):
    @property
    def name(self) -> str:
        return self.item.get("label") or self.item_name

    @property
    def is_on(self) -> bool | None:
        state = self.item.get("state")
        if state in NULL_STATES:
            return None
        return str(state).upper() in {"ON", "OPEN", "TRUE", "1", "ALARM"}

    @property
    def device_class(self):
        text = f"{self.item.get('category', '')} {self.item.get('label', '')}".lower()
        if "window" in text or "fenster" in text:
            return BinarySensorDeviceClass.WINDOW
        if "door" in text or "tür" in text:
            return BinarySensorDeviceClass.DOOR
        if "motion" in text or "beweg" in text:
            return BinarySensorDeviceClass.MOTION
        if "battery" in text or "batter" in text:
            return BinarySensorDeviceClass.BATTERY
        if "alarm" in text or "error" in text:
            return BinarySensorDeviceClass.PROBLEM
        return None
