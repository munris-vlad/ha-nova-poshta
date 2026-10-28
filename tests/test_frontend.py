"""Cold-start registration must be awaited, idempotent and preserve other cards."""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.lovelace.resources import ResourceStorageCollection
from custom_components.nova_poshta_account.frontend import CARD_PATH, CARD_URL, async_register_card


class FrontendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.items = [{"id":"other", "url":"/hacsfiles/other/card.js", "type":"module"}]
        self.loaded = False
        self.resources = MagicMock(spec=ResourceStorageCollection)
        async def load():
            self.loaded = True
        def items():
            self.assertTrue(self.loaded, "Storage must load before inspecting resources")
            return self.items
        async def create(data):
            self.assertTrue(self.loaded)
            self.items.append({"id":"nova", "url":data["url"], "type":data["res_type"]})
        self.resources.async_get_info = AsyncMock(side_effect=load)
        self.resources.async_items.side_effect = items
        self.resources.async_create_item = AsyncMock(side_effect=create)
        self.resources.async_update_item = AsyncMock()
        self.hass = SimpleNamespace(data={"lovelace":SimpleNamespace(resources=self.resources)},
                                    http=SimpleNamespace(async_register_static_paths=AsyncMock()))

    async def test_cold_start_preserves_other_resources(self):
        await async_register_card(self.hass)
        self.assertEqual(self.items[0], {"id":"other", "url":"/hacsfiles/other/card.js", "type":"module"})
        self.assertEqual(self.items[1]["url"], CARD_URL)
        self.assertEqual(self.items[1]["type"], "module")

    async def test_repeated_setup_does_not_duplicate_resource_or_route(self):
        await async_register_card(self.hass)
        await async_register_card(self.hass)
        self.assertEqual(len(self.items), 2)
        self.resources.async_create_item.assert_awaited_once()
        self.hass.http.async_register_static_paths.assert_awaited_once()

    async def test_upgrade_changes_only_our_existing_resource(self):
        self.items.append({"id":"nova", "url":CARD_PATH+"?v=0.3.0", "type":"module"})
        await async_register_card(self.hass)
        self.resources.async_update_item.assert_awaited_once_with("nova", {"url":CARD_URL, "res_type":"module"})
        self.resources.async_create_item.assert_not_called()
        self.assertEqual(self.items[0]["url"], "/hacsfiles/other/card.js")

    async def test_yaml_resources_are_not_overwritten(self):
        yaml_resources = SimpleNamespace(async_items=lambda: [])
        self.hass.data["lovelace"].resources = yaml_resources
        with self.assertLogs("custom_components.nova_poshta_account.frontend", level="WARNING") as logs:
            await async_register_card(self.hass)
        self.assertIn(CARD_URL, logs.output[0])


if __name__ == "__main__":
    unittest.main()
