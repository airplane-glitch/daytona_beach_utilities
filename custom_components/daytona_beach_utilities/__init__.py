"""Daytona Beach Utilities: bills and water usage from the City of Daytona Beach customer portal."""
from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import DaytonaPortal
from .coordinator import DaytonaConfigEntry, DaytonaCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: DaytonaConfigEntry) -> bool:
    # A session of its own, so the portal's sign-in cookies are not shared with anything else in Home Assistant.
    session = async_create_clientsession(hass)
    portal = DaytonaPortal(session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = DaytonaCoordinator(hass, entry, portal)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DaytonaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
