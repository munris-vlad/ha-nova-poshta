"""Configure account key and polling through the Home Assistant interface."""
import hashlib

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import ApiError, AuthenticationError, NovaPoshtaApi
from .const import DEFAULT_DAYS, DEFAULT_DIRECTION, DEFAULT_INTERVAL, DOMAIN


def settings_schema(defaults):
    return {
        vol.Required("direction", default=defaults.get("direction", DEFAULT_DIRECTION)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=["incoming", "outgoing", "both"], translation_key="direction")),
        vol.Required("scan_interval", default=defaults.get("scan_interval", DEFAULT_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
        vol.Required("lookback_days", default=defaults.get("lookback_days", DEFAULT_DAYS)): vol.All(vol.Coerce(int), vol.Range(min=1, max=730)),
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input = {**user_input, CONF_API_KEY: user_input[CONF_API_KEY].strip()}
            await self.async_set_unique_id(hashlib.sha256(user_input[CONF_API_KEY].encode()).hexdigest())
            self._abort_if_unique_id_configured()
            try:
                await NovaPoshtaApi(async_get_clientsession(self.hass), user_input[CONF_API_KEY]).parcels(
                    dt_util.now(), user_input["lookback_days"], user_input["direction"])
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except ApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="Nova Poshta · My Parcels", data=user_input)
        schema = {vol.Required(CONF_API_KEY): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)), **settings_schema(user_input or {})}
        return self.async_show_form(step_id="user", data_schema=vol.Schema(schema), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            entry = self._get_reauth_entry()
            try:
                await NovaPoshtaApi(async_get_clientsession(self.hass), key).parcels(dt_util.now(), 1, "incoming")
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except ApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(hashlib.sha256(key.encode()).hexdigest())
                if any(other.entry_id != entry.entry_id and other.unique_id == self.unique_id
                       for other in self._async_current_entries()):
                    return self.async_abort(reason="already_configured")
                self.hass.config_entries.async_update_entry(entry, unique_id=self.unique_id)
                return self.async_update_reload_and_abort(entry, data_updates={CONF_API_KEY: key})
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_API_KEY): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            options = dict(user_input)
            key = options.pop(CONF_API_KEY, "").strip() or self.config_entry.data[CONF_API_KEY]
            unique_id = hashlib.sha256(key.encode()).hexdigest()
            if any(entry.entry_id != self.config_entry.entry_id and entry.unique_id == unique_id
                   for entry in self.hass.config_entries.async_entries(DOMAIN)):
                errors["base"] = "already_configured"
            else:
                try:
                    await NovaPoshtaApi(async_get_clientsession(self.hass), key).parcels(
                        dt_util.now(), options["lookback_days"], options["direction"])
                except AuthenticationError:
                    errors["base"] = "invalid_auth"
                except ApiError:
                    errors["base"] = "cannot_connect"
                else:
                    if key != self.config_entry.data[CONF_API_KEY]:
                        # Save credentials only in entry data, never in options.
                        # Commit key and polling settings together: one reload.
                        self.hass.config_entries.async_update_entry(
                            self.config_entry, data={**self.config_entry.data, CONF_API_KEY: key},
                            unique_id=unique_id, options=options)
                    return self.async_create_entry(title="", data=options)
        defaults = {**self.config_entry.data, **self.config_entry.options, **(user_input or {})}
        schema = {vol.Optional(CONF_API_KEY): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)), **settings_schema(defaults)}
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
