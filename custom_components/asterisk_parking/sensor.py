"""Parking slot sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Create one sensor per configured parking slot."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ParkingSlotSensor(coordinator, entry.entry_id, slot)
        for slot in coordinator.slots
    )


class ParkingSlotSensor(CoordinatorEntity, SensorEntity):
    """Represent one Asterisk parking space."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:phone-in-talk"

    def __init__(self, coordinator, entry_id: str, slot: str) -> None:
        """Initialize a parking sensor."""
        super().__init__(coordinator)
        self._slot = slot
        self._attr_unique_id = f"{entry_id}_parking_{slot}"
        self._attr_name = f"Parking {slot}"

    @property
    def native_value(self) -> str:
        """Return a human-readable parking status."""
        status = self.coordinator.data[self._slot]["status"]
        return {
            "free": "Free",
            "waiting": "Call Waiting",
            "unknown": "Unknown",
        }.get(status, "Unknown")

    @property
    def extra_state_attributes(self) -> dict:
        """Expose optional call details."""
        details = self.coordinator.data[self._slot]
        return {
            "parking_slot": self._slot,
            "parking_lot": self.coordinator.parkinglot,
            "caller_id": details.get("caller_id"),
            "caller_id_number": details.get("caller_id"),
            "caller_id_name": details.get("caller_id_name"),
            "channel": details.get("channel"),
        }
