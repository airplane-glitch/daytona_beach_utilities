"""Polls the portal and shares the result with every sensor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, DaytonaPortal, PortalError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type DaytonaConfigEntry = ConfigEntry[DaytonaCoordinator]


class DaytonaCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Data is {account number: account data}, one entry for each house on the login."""

    def __init__(self, hass: HomeAssistant, entry: DaytonaConfigEntry, portal: DaytonaPortal) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL, config_entry=entry)
        self.portal = portal

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            return await self.portal.fetch_all()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PortalError as err:
            raise UpdateFailed(str(err)) from err
