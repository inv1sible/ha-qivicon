"""QIVICON light entities."""

from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
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
        if item.get("type") != "Dimmer":
            continue
        text = f"{item.get('name', '')} {item.get('label', '')}".lower()
        if not item_is_writable(item) or not (
            "brightness" in text or "helligkeit" in text
        ):
            continue
        entities.append(
            QiviconLight(
                coordinator,
                item["name"],
                item_device_id(item, coordinator.data.devices, coordinator.data.items),
            )
        )
    async_add_entities(entities)


class QiviconLight(QiviconEntity, LightEntity):
    """A dimmable QIVICON light."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def name(self) -> str:
        device = self.device
        return device.get("label", "Light") if device else self.item.get("label", "Light")

    @property
    def _level(self) -> float | None:
        state = self.item.get("state")
        if state in NULL_STATES:
            return None
        try:
            return max(0, min(100, float(state)))
        except (TypeError, ValueError):
            return None

    @property
    def is_on(self) -> bool | None:
        level = self._level
        return None if level is None else level > 0

    @property
    def brightness(self) -> int | None:
        level = self._level
        return None if level is None else round(level * 255 / 100)

    async def async_turn_on(self, **kwargs) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        level = 100 if brightness is None else round(brightness * 100 / 255)
        await self.coordinator.client.send_item_command(self.item_name, str(level))
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.send_item_command(self.item_name, "0")
        await self.coordinator.async_request_refresh()
