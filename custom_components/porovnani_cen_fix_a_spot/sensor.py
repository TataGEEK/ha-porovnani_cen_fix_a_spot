from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DOMAIN,
    ATTR_SOURCE_ENTITY_ID,
    ATTR_SOURCE_STATE,
    ATTR_IS_LOW_TARIFF,
)


class HDOTariffSensor(SensorEntity):
    """Sensor odvozující HDO tarif z přepínače (ON=nízký, OFF=vysoký)."""

    _attr_icon = "mdi:flash-auto"

    def __init__(self, hass: HomeAssistant, source_entity_id: str) -> None:
        self.hass = hass
        self._source_entity_id = source_entity_id
        self._unsubscribe = None
        self._attr_name = "HDO Tarif"
        safe_source = (
            source_entity_id.replace(".", "_").replace(":", "_").replace("/", "_")
        )
        self._attr_unique_id = f"{DOMAIN}_hdo_tarif_{safe_source}"
        self._state = None
        self._attrs = {}

    async def async_added_to_hass(self) -> None:
        # Inicializace stavu z aktuálního zdrojového entity
        self._set_from_source(self.hass.states.get(self._source_entity_id))

        @callback
        def _state_change(event):
            new_state = event.data.get("new_state")
            self._set_from_source(new_state)

        self._unsubscribe = async_track_state_change_event(
            self.hass, [self._source_entity_id], _state_change
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _set_from_source(self, state_obj) -> None:
        if state_obj is None:
            self._state = "neznámé"
            self._attrs = {
                ATTR_SOURCE_ENTITY_ID: self._source_entity_id,
                ATTR_SOURCE_STATE: None,
                ATTR_IS_LOW_TARIFF: None,
            }
        else:
            src_state = state_obj.state
            # ON/true/1 => nízký tarif, jinak vysoký
            is_low = str(src_state).lower() in ("on", "true", "1")
            self._state = "nízký" if is_low else "vysoký"
            self._attrs = {
                ATTR_SOURCE_ENTITY_ID: self._source_entity_id,
                ATTR_SOURCE_STATE: src_state,
                ATTR_IS_LOW_TARIFF: is_low,
            }
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attrs


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    source_entity_id = hass.data[DOMAIN][entry.entry_id]["source_entity_id"]
    async_add_entities([HDOTariffSensor(hass, source_entity_id)], True)
