"""QIVICON sensor entities."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import QiviconConfigEntry
from .const import DOMAIN, NULL_STATES
from .coordinator import QiviconCoordinator
from .entity import QiviconEntity, item_device_id, item_is_visible, item_is_writable


async def async_setup_entry(
    hass, entry: QiviconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities = []
    for device in coordinator.data.devices:
        if device.get("isBridge"):
            entities.extend(
                (
                    QiviconBridgeDiagnostic(coordinator, device["id"], "status"),
                    QiviconBridgeDiagnostic(coordinator, device["id"], "firmware"),
                )
            )
    for item in coordinator.data.items:
        item_type = item.get("type") or ""
        if not item_type.startswith(("Number", "String", "DateTime")):
            continue
        if item_is_writable(item) or not item_is_visible(
            item, coordinator.data.devices, coordinator.data.items
        ):
            continue
        entities.append(
            QiviconSensor(
                coordinator,
                item["name"],
                item_device_id(item, coordinator.data.devices, coordinator.data.items),
            )
        )
    async_add_entities(entities)


class QiviconBridgeDiagnostic(CoordinatorEntity[QiviconCoordinator], SensorEntity):
    """Useful bridge metadata QIVICON exposes outside its item inventory."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: QiviconCoordinator, bridge_id: str, kind: str) -> None:
        super().__init__(coordinator)
        self.bridge_id = bridge_id
        self.kind = kind
        self._attr_unique_id = f"{coordinator.client.host}_{bridge_id}_{kind}"
        self._attr_translation_key = kind

    @property
    def bridge(self) -> dict[str, Any]:
        return next(
            (
                device
                for device in self.coordinator.data.devices
                if device.get("id") == self.bridge_id
            ),
            {},
        )

    @property
    def native_value(self) -> str | None:
        detail = self.bridge.get("detail") or {}
        if self.kind == "firmware":
            return detail.get("firmwareVersion")
        return (self.bridge.get("deviceStatus") or {}).get("status")

    @property
    def device_info(self) -> DeviceInfo:
        detail = self.bridge.get("detail") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self.bridge_id)},
            name=self.bridge.get("label") or self.bridge_id,
            manufacturer=detail.get("vendor") or "QIVICON",
            model=detail.get("model") or self.bridge.get("thingTypeId"),
            sw_version=detail.get("firmwareVersion"),
            via_device=(DOMAIN, f"hub_{self.coordinator.client.host}"),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        detail = self.bridge.get("detail") or {}
        condition = self.bridge.get("condition") or {}
        status = self.bridge.get("deviceStatus") or {}
        return {
            "connection": detail.get("connection"),
            "last_communication_success": condition.get("lastCommunicationSuccess"),
            "last_communication_failure": condition.get("lastCommunicationFailure"),
            "status_detail": status.get("statusDetail"),
            "status_description": status.get("statusDescription"),
        }


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
        tags = self.item.get("tags") or []
        if category == "temperature":
            return SensorDeviceClass.TEMPERATURE
        if category == "humidity":
            return SensorDeviceClass.HUMIDITY
        if category == "battery":
            return SensorDeviceClass.BATTERY
        if category == "power" or "property:power" in tags:
            return SensorDeviceClass.POWER
        if category == "energy" or "property:energy" in tags:
            return SensorDeviceClass.ENERGY
        if "property:current" in tags:
            return SensorDeviceClass.CURRENT
        if "property:voltage" in tags:
            return SensorDeviceClass.VOLTAGE
        if "property:frequency" in tags:
            return SensorDeviceClass.FREQUENCY
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        pattern = (self.item.get("stateDescription") or {}).get("pattern", "")
        if "°C" in pattern:
            return UnitOfTemperature.CELSIUS
        match = re.search(r"%[^ ]+\s+(.+)$", pattern)
        return match.group(1) if match else None
