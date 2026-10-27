"""Nova Poshta account parcels."""
import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApiError, AuthenticationError, NovaPoshtaApi
from .const import DEFAULT_DAYS, DEFAULT_DIRECTION, DEFAULT_INTERVAL, DOMAIN

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]
LOGGER = logging.getLogger(__name__)
CARD_VERSION = "0.2.1"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass, config):
    """Load the bundled card once, independently of account credentials."""
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths([
        StaticPathConfig(f"/{DOMAIN}/frontend", str(frontend_dir), False)
    ])
    add_extra_js_url(hass, f"/{DOMAIN}/frontend/nova-poshta-account-card.js?v={CARD_VERSION}")
    return True


class ParcelCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.api = NovaPoshtaApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])
        self.settings = {**entry.data, **entry.options}
        self.last_success = None
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(minutes=self.settings.get("scan_interval", DEFAULT_INTERVAL)))

    async def _async_update_data(self):
        try:
            rows = await self.api.parcels(dt_util.now(), self.settings.get("lookback_days", DEFAULT_DAYS),
                                          self.settings.get("direction", DEFAULT_DIRECTION))
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed("API key was rejected") from err
        except ApiError as err:
            raise UpdateFailed(str(err)) from err
        self.last_success = dt_util.utcnow().isoformat()
        return rows


async def async_setup_entry(hass, entry):
    coordinator = ParcelCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
