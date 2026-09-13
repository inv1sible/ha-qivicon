"""QIVICON light entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import QiviconConfigEntry
from .const import NULL_STATES
from .entity import QiviconEntity, item_device_id, item_is_writable

MIN_COLOR_TEMP_KELVIN = 2000
MAX_COLOR_TEMP_KELVIN = 6500


async def async_setup_entry(
    hass, entry: QiviconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    channels_by_device: dict[str, dict[str, str]] = {}

    for item in coordinator.data.items:
        if not item_is_writable(item):
            continue
        tags = item.get("tags") or []
        item_type = item.get("type")
        if item_type not in ("Dimmer", "Color") or "property:light" not in tags:
            continue

        device_id = item_device_id(
            item, coordinator.data.devices, coordinator.data.items
        )
        key = device_id or item["name"]
        channels = channels_by_device.setdefault(key, {"device_id": device_id})
        if item_type == "Color" or "capability:color" in tags:
            channels["color"] = item["name"]
        elif "capability:colorTemperature" in tags:
            channels["color_temperature"] = item["name"]
        else:
            channels["brightness"] = item["name"]

    entities = []
    for channels in channels_by_device.values():
        primary = (
            channels.get("brightness")
            or channels.get("color")
            or channels["color_temperature"]
        )
        entities.append(
            QiviconLight(
                coordinator,
                primary,
                channels.get("device_id"),
                channels,
            )
        )
    async_add_entities(entities)


def _level(value: Any) -> float | None:
    if value in NULL_STATES:
        return None
    try:
        return max(0, min(100, float(value)))
    except (TypeError, ValueError):
        return None


def _hsb(value: Any) -> tuple[float, float, float] | None:
    if value in NULL_STATES:
        return None
    try:
        hue, saturation, brightness = (float(part) for part in str(value).split(","))
        return hue % 360, max(0, min(100, saturation)), max(0, min(100, brightness))
    except (TypeError, ValueError):
        return None


class QiviconLight(QiviconEntity, LightEntity):
    """A composite QIVICON light backed by one or more item channels."""

    def __init__(self, coordinator, item_name, device_id, channels) -> None:
        super().__init__(coordinator, item_name, device_id)
        self.channels = channels

    def _channel(self, kind: str) -> dict[str, Any]:
        name = self.channels.get(kind)
        return next(
            (item for item in self.coordinator.data.items if item.get("name") == name),
            {},
        )

    @property
    def name(self) -> str:
        device = self.device
        return device.get("label", "Light") if device else self.item.get("label", "Light")

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        if self.channels.get("color"):
            modes = {ColorMode.HS}
            if self.channels.get("color_temperature"):
                modes.add(ColorMode.COLOR_TEMP)
            return modes
        if self.channels.get("color_temperature"):
            return {ColorMode.COLOR_TEMP}
        return {ColorMode.BRIGHTNESS}

    @property
    def color_mode(self) -> ColorMode:
        if self.channels.get("color"):
            mode_item = next(
                (
                    item
                    for item in self.coordinator.data.items
                    if self.qivicon_device_id
                    == item_device_id(
                        item,
                        self.coordinator.data.devices,
                        self.coordinator.data.items,
                    )
                    and "type:colorMode" in (item.get("tags") or [])
                ),
                {},
            )
            if mode_item.get("state") == "TW" and self.channels.get("color_temperature"):
                return ColorMode.COLOR_TEMP
            return ColorMode.HS
        if self.channels.get("color_temperature"):
            return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS

    @property
    def brightness(self) -> int | None:
        level = _level(self._channel("brightness").get("state"))
        if level is None and (color := _hsb(self._channel("color").get("state"))):
            level = color[2]
        return None if level is None else round(level * 255 / 100)

    @property
    def is_on(self) -> bool | None:
        brightness = self.brightness
        return None if brightness is None else brightness > 0

    @property
    def hs_color(self) -> tuple[float, float] | None:
        color = _hsb(self._channel("color").get("state"))
        return None if color is None else (color[0], color[1])

    @property
    def min_color_temp_kelvin(self) -> int:
        return MIN_COLOR_TEMP_KELVIN

    @property
    def max_color_temp_kelvin(self) -> int:
        return MAX_COLOR_TEMP_KELVIN

    @property
    def color_temp_kelvin(self) -> int | None:
        level = _level(self._channel("color_temperature").get("state"))
        if level is None:
            return None
        return round(
            MIN_COLOR_TEMP_KELVIN
            + level / 100 * (MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN)
        )

    async def async_turn_on(self, **kwargs) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        hs_color = kwargs.get(ATTR_HS_COLOR)
        color_temp = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        color_name = self.channels.get("color")
        brightness_name = self.channels.get("brightness")

        if hs_color is not None and color_name:
            level = 100 if brightness is None else round(brightness * 100 / 255)
            hue, saturation = hs_color
            await self.coordinator.client.send_item_command(
                color_name, f"{hue:g},{saturation:g},{level:g}"
            )
        elif brightness is not None:
            level = round(brightness * 100 / 255)
            target = brightness_name or color_name
            if target:
                await self.coordinator.client.send_item_command(target, str(level))

        if color_temp is not None and self.channels.get("color_temperature"):
            normalized = round(
                100
                * (color_temp - MIN_COLOR_TEMP_KELVIN)
                / (MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN)
            )
            normalized = max(0, min(100, normalized))
            await self.coordinator.client.send_item_command(
                self.channels["color_temperature"], str(normalized)
            )

        if brightness is None and hs_color is None and color_temp is None:
            target = brightness_name or color_name or self.channels.get("color_temperature")
            await self.coordinator.client.send_item_command(target, "ON")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        target = (
            self.channels.get("brightness")
            or self.channels.get("color")
            or self.channels["color_temperature"]
        )
        await self.coordinator.client.send_item_command(target, "OFF")
        await self.coordinator.async_request_refresh()
