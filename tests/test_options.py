"""Credential changes must validate before saving and keep keys out of forms/options.

Run inside the Home Assistant runtime together with test_api.py.
"""
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.nova_poshta_account import config_flow
from custom_components.nova_poshta_account.api import ApiError, AuthenticationError


class OptionsFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = SimpleNamespace(entry_id="test-entry", data={"api_key":"existing-test-key", "direction":"both", "scan_interval":15, "lookback_days":365}, options={}, unique_id="previous")
        manager = MagicMock()
        manager.async_get_known_entry.return_value = self.entry
        manager.async_entries.return_value = [self.entry]
        self.flow = config_flow.OptionsFlow()
        self.flow.hass = SimpleNamespace(config_entries=manager)
        self.flow.handler = "test-entry"
        self.flow.flow_id = "options-test"
        self.flow.context = {}
        self.input = {"direction":"incoming", "scan_interval":20, "lookback_days":180}
        self.client = MagicMock()
        self.client.parcels = AsyncMock(return_value=[])
        self.api_patch = patch.object(config_flow, "NovaPoshtaApi", return_value=self.client)
        self.session_patch = patch.object(config_flow, "async_get_clientsession", return_value=object())
        self.factory = self.api_patch.start()
        self.session_patch.start()
        self.addCleanup(self.api_patch.stop)
        self.addCleanup(self.session_patch.stop)

    async def test_empty_key_keeps_existing_credential(self):
        result = await self.flow.async_step_init({**self.input,"api_key":"  "})
        self.assertEqual(result["type"], "create_entry")
        self.assertNotIn("api_key",result["data"])
        self.assertEqual(self.factory.call_args.args[1], "existing-test-key")
        self.flow.hass.config_entries.async_update_entry.assert_not_called()

    async def test_valid_key_saved_in_data_and_settings_in_one_commit(self):
        result = await self.flow.async_step_init({**self.input,"api_key":"  replacement-test-key  "})
        self.assertEqual(result["type"], "create_entry")
        manager = self.flow.hass.config_entries
        manager.async_update_entry.assert_called_once()
        saved = manager.async_update_entry.call_args.kwargs
        self.assertEqual(saved["data"]["api_key"], "replacement-test-key")
        self.assertEqual(saved["unique_id"], hashlib.sha256(b"replacement-test-key").hexdigest())
        self.assertNotIn("api_key",saved["options"])
        self.assertNotIn("api_key",result["data"])

    async def test_rejected_key_does_not_change_existing_settings(self):
        self.client.parcels.side_effect = AuthenticationError("Rejected")
        result = await self.flow.async_step_init({**self.input,"api_key":"invalid-test-key"})
        self.assertEqual(result["errors"], {"base":"invalid_auth"})
        self.flow.hass.config_entries.async_update_entry.assert_not_called()

    async def test_network_failure_does_not_change_existing_settings(self):
        self.client.parcels.side_effect = ApiError("Unavailable")
        result = await self.flow.async_step_init({**self.input,"api_key":"replacement-test-key"})
        self.assertEqual(result["errors"], {"base":"cannot_connect"})
        self.flow.hass.config_entries.async_update_entry.assert_not_called()

    async def test_duplicate_account_is_not_saved(self):
        other = SimpleNamespace(entry_id="other-entry", unique_id=hashlib.sha256(b"duplicate-key").hexdigest())
        self.flow.hass.config_entries.async_entries.return_value = [self.entry, other]
        result = await self.flow.async_step_init({**self.input,"api_key":"duplicate-key"})
        self.assertEqual(result["errors"], {"base":"already_configured"})
        self.client.parcels.assert_not_called()
        self.flow.hass.config_entries.async_update_entry.assert_not_called()

    async def test_current_key_is_not_prefilled_in_form(self):
        result = await self.flow.async_step_init()
        schema = result["data_schema"].schema
        key = next(key for key in schema if str(key)=="api_key")
        self.assertIs(key.default, config_flow.vol.UNDEFINED)


if __name__ == "__main__":
    unittest.main()
