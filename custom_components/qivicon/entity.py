"""Shared QIVICON entity helpers."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import QiviconCoordinator


def thing_uid_from_item(item: dict[str, Any]) -> str | None:
    for tag in item.get("tags") or []:
        if tag.startswith("THING_UID="):
            return tag.removeprefix("THING_UID=")
    return None


def item_is_writable(item: dict[str, Any]) -> bool:
    """Return whether QIVICON advertises an item as writable."""
    tags = item.get("tags") or []
    description = item.get("stateDescription") or {}
    return (
        "capability:control" in tags
        or "capability:switchable" in tags
        or description.get("readOnly") is False
    )


def item_device_id(
    item: dict[str, Any],
    devices: list[dict[str, Any]],
    all_items: list[dict[str, Any]] | None = None,
) -> str | None:
    groups = set(item.get("groupNames") or [])
    for device in devices:
        device_group = device["id"].replace(":", "_").replace("-", "_")
        if device_group in groups:
            return device["id"]
    if all_items:
        for group in groups:
            group_item = next(
                (candidate for candidate in all_items if candidate.get("name") == group),
                None,
            )
            if group_item and (uid := thing_uid_from_item(group_item)):
                return uid
    return thing_uid_from_item(item)


def item_device(
    item: dict[str, Any],
    devices: list[dict[str, Any]],
    all_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return the QIVICON device that owns an item, if known."""
    device_id = item_device_id(item, devices, all_items)
    return next((device for device in devices if device.get("id") == device_id), None)


def item_is_visible(
    item: dict[str, Any],
    devices: list[dict[str, Any]],
    all_items: list[dict[str, Any]] | None = None,
) -> bool:
    """Hide infrastructure counters and known internal Homematic channels.

    The raw item inventory exposes a large number of implementation channels.
    They are not useful Home Assistant controls and, in several cases, are
    permanently NULL.  Keep the actual switch, measurements and communication
    error from HMIP-PSM plugs while omitting their virtual schedules/profiles.
    """
    device = item_device(item, devices, all_items)
    if not device:
        return True
    if device.get("isBridge"):
        return False
    if (device.get("detail") or {}).get("model") != "HMIP-PSM":
        return True
    tags = set(item.get("tags") or [])
    return (
        "capability:switchable" in tags
        or "capability:measurement" in tags
        or "capability:signalStrength" in tags
        or item.get("name", "").endswith("_00_UNREACH")
    )


class QiviconEntity(CoordinatorEntity[QiviconCoordinator]):
    """Base entity backed by a QIVICON item."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: QiviconCoordinator,
        item_name: str,
        device_id: str | None,
    ) -> None:
        super().__init__(coordinator)
        self.item_name = item_name
        self.qivicon_device_id = device_id
        self._attr_unique_id = f"{coordinator.client.host}_{item_name}"

    @property
    def item(self) -> dict[str, Any]:
        return next(
            (item for item in self.coordinator.data.items if item.get("name") == self.item_name),
            {},
        )

    @property
    def device(self) -> dict[str, Any] | None:
        return next(
            (
                device
                for device in self.coordinator.data.devices
                if device.get("id") == self.qivicon_device_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        device = self.device
        return super().available and (
            device is None or device.get("deviceStatus", {}).get("status") == "ONLINE"
        )

    @property
    def device_info(self) -> DeviceInfo | None:
        device = self.device
        if device is None:
            return None
        detail = device.get("detail") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, device["id"])},
            name=device.get("label") or device["id"],
            manufacturer=detail.get("vendor") or "QIVICON",
            model=detail.get("model") or device.get("thingTypeId"),
            sw_version=detail.get("firmwareVersion"),
            via_device=(DOMAIN, f"hub_{self.coordinator.client.host}"),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw capability metadata needed for unsupported devices."""
        item = self.item
        description = item.get("stateDescription") or {}
        return {
            "qivicon_item": self.item_name,
            "qivicon_type": item.get("type"),
            "qivicon_category": item.get("category"),
            "qivicon_tags": item.get("tags") or [],
            "qivicon_read_only": description.get("readOnly"),
            "qivicon_minimum": description.get("minimum"),
            "qivicon_maximum": description.get("maximum"),
            "qivicon_step": description.get("step"),
            "qivicon_options": description.get("options") or [],
        }
