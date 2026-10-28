"""Register the bundled card as an awaited dashboard resource."""
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection

from .const import DOMAIN

LOGGER = logging.getLogger(__name__)
CARD_VERSION = "0.3.1"
CARD_PATH = f"/{DOMAIN}/frontend/nova-poshta-account-card.js"
CARD_URL = f"{CARD_PATH}?v={CARD_VERSION}"


async def async_register_card(hass):
    """Keep other resources intact and register once, updating our URL on upgrade."""
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("frontend_path_registered"):
        await hass.http.async_register_static_paths([
            StaticPathConfig(f"/{DOMAIN}/frontend", str(Path(__file__).parent / "frontend"), False)
        ])
        data["frontend_path_registered"] = True

    resources = hass.data[LOVELACE_DATA].resources
    if not isinstance(resources, ResourceStorageCollection):
        # YAML resources are user-managed. Do not mutate the user's YAML or
        # silently fall back to non-awaited extra_module_url loading.
        if not any(item.get("url", "").split("?")[0] == CARD_PATH for item in resources.async_items()):
            LOGGER.warning("Add %s as a module resource to your YAML Lovelace resources", CARD_URL)
        return

    # This public method ensures lazy storage is loaded before reading/writing.
    # Otherwise an early startup registration can erase unrelated resources.
    await resources.async_get_info()
    existing = next((item for item in resources.async_items()
                     if item.get("url", "").split("?")[0] == CARD_PATH), None)
    if existing is None:
        await resources.async_create_item({"url": CARD_URL, "res_type": "module"})
    elif existing.get("url") != CARD_URL or existing.get("type") != "module":
        await resources.async_update_item(existing["id"], {"url": CARD_URL, "res_type": "module"})
