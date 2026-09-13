"""QIVICON data coordinator."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import QiviconClient, QiviconError, QiviconSnapshot
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class QiviconCoordinator(DataUpdateCoordinator[QiviconSnapshot]):
    """Fetch shared QIVICON data."""

    def __init__(self, hass: HomeAssistant, client: QiviconClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> QiviconSnapshot:
        try:
            return await self.client.get_snapshot()
        except QiviconError as err:
            raise UpdateFailed(str(err)) from err
