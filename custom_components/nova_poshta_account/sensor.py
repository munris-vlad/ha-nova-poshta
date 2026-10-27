"""Summary sensors with a compact list of active parcels."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ParcelSensor(entry, "active"), ParcelSensor(entry, "pickup")])


class ParcelSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({"parcels", "last_update"})

    def __init__(self, entry, kind):
        super().__init__(entry.runtime_data)
        self.kind = kind
        self._attr_unique_id = f"{entry.entry_id}_{kind}"
        self._attr_translation_key = kind
        self._attr_icon = "mdi:package-variant" if kind == "active" else "mdi:package-check"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, translation_key="account", manufacturer="Nova Poshta")

    @property
    def native_value(self):
        rows = self.coordinator.data or []
        return len(rows) if self.kind == "active" else sum(p["status"] == "at_pickup_point" for p in rows)

    @property
    def extra_state_attributes(self):
        if self.kind == "pickup":
            return None
        refresh = er.async_get(self.hass).async_get_entity_id(
            "button", DOMAIN, self.unique_id.removesuffix("_active") + "_refresh")
        return {"integration": DOMAIN, "refresh_entity": refresh,
                "parcels": self.coordinator.data or [], "last_update": self.coordinator.last_success,
                "lookback_days": self.coordinator.settings.get("lookback_days", 365)}
