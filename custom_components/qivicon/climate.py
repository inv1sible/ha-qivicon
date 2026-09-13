"""QIVICON thermostat entities."""

from __future__ import annotations

import re

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import QiviconConfigEntry
from .const import NULL_STATES
from .entity import QiviconEntity, item_device_id


async def async_setup_entry(
    hass, entry: QiviconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    by_group: dict[str, list[dict]] = {}
    for item in coordinator.data.items:
        for group in item.get("groupNames") or []:
            by_group.setdefault(group, []).append(item)

    entities = []
    for items in by_group.values():
        target = next(
            (
                item
                for item in items
                if (item.get("type") or "").startswith("Number")
                and "property:temperature" in (item.get("tags") or [])
                and "capability:control" in (item.get("tags") or [])
            ),
            None,
        )
        current = next(
            (
                item
                for item in items
                if (item.get("type") or "").startswith("Number")
                and "property:temperature" in (item.get("tags") or [])
                and "capability:measurement" in (item.get("tags") or [])
            ),
            None,
        )
        if target:
            entities.append(
                QiviconClimate(
                    coordinator,
                    target["name"],
                    current["name"] if current else None,
                    item_device_id(
                        target, coordinator.data.devices, coordinator.data.items
                    ),
                )
            )
    async_add_entities(entities)


def _float_state(item: dict | None) -> float | None:
    if not item or item.get("state") in NULL_STATES:
        return None
    try:
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(item["state"]))
        return float(match.group(0).replace(",", ".")) if match else None
    except (TypeError, ValueError):
        return None


class QiviconClimate(QiviconEntity, ClimateEntity):
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, target_name, current_name, device_id) -> None:
        super().__init__(coordinator, target_name, device_id)
        self.current_item_name = current_name

    @property
    def name(self) -> str:
        device = self.device
        return device.get("label", "Thermostat") if device else "Thermostat"

    @property
    def current_item(self) -> dict | None:
        return next(
            (
                item
                for item in self.coordinator.data.items
                if item.get("name") == self.current_item_name
            ),
            None,
        )

    @property
    def current_temperature(self) -> float | None:
        return _float_state(self.current_item)

    @property
    def target_temperature(self) -> float | None:
        return _float_state(self.item)

    @property
    def min_temp(self) -> float:
        return float((self.item.get("stateDescription") or {}).get("minimum", 5))

    @property
    def max_temp(self) -> float:
        return float((self.item.get("stateDescription") or {}).get("maximum", 30))

    @property
    def target_temperature_step(self) -> float:
        return float((self.item.get("stateDescription") or {}).get("step", 0.5))

    async def async_set_temperature(self, **kwargs) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.client.send_item_command(
            self.item_name, f"{float(temperature):g}"
        )
        await self.coordinator.async_request_refresh()
