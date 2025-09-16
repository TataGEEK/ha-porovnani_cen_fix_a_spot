from __future__ import annotations

import logging
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone
from calendar import monthrange

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass       # type: ignore
from homeassistant.const import UnitOfEnergy                                                        # type: ignore
from homeassistant.core import HomeAssistant, callback, State                                       # type: ignore
from homeassistant.helpers.entity_platform import AddEntitiesCallback                               # type: ignore
from homeassistant.helpers.restore_state import RestoreEntity                                       # type: ignore
from homeassistant.config_entries import ConfigEntry                                                # type: ignore
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change     # type: ignore

LOGGER = logging.getLogger(__name__)

from .const import (
    DOMAIN,
    ATTR_SOURCE_ENTITY_ID, ATTR_SOURCE_STATE, ATTR_IS_LOW_TARIFF,
    # --- FIX ---
    CONF_FIX_OBCHODNI_CENA_VT, CONF_FIX_OBCHODNI_CENA_NT,
    CONF_FIX_STALA_PLATBA, CONF_FIX_ZA_JISTIC, CONF_FIX_PROVOZ_INFRASTRUKTURY,
    DEFAULT_FIX_OBCHODNI_CENA_VT, DEFAULT_FIX_OBCHODNI_CENA_NT,
    DEFAULT_FIX_STALA_PLATBA, DEFAULT_FIX_ZA_JISTIC, DEFAULT_FIX_PROVOZ_INFRASTRUKTURY,
    # --- SPOT ---
    CONF_SPOT_MARZE, CONF_SPOT_STALA_PLATBA, CONF_SPOT_ZA_JISTIC, CONF_SPOT_PROVOZ_INFRASTRUKTURY,
    DEFAULT_SPOT_MARZE, DEFAULT_SPOT_STALA_PLATBA, DEFAULT_SPOT_ZA_JISTIC, DEFAULT_SPOT_PROVOZ_INFRASTRUKTURY,
    # --- POZE / DISTRIBUCE ---
    CONF_POZE, DEFAULT_POZE,
    CONF_DISTRIBUCE_VT, CONF_DISTRIBUCE_NT, CONF_DISTRIBUCE_DAN, CONF_DISTRIBUCE_SLUZBY,
    DEFAULT_DISTRIBUCE_VT, DEFAULT_DISTRIBUCE_NT, DEFAULT_DISTRIBUCE_DAN, DEFAULT_DISTRIBUCE_SLUZBY,
    # --- spotřeba ---
    CONF_CONS_TOTAL_ENERGY, CONF_CONS_PHASE1, CONF_CONS_PHASE2, CONF_CONS_PHASE3,
    # --- spot price ---
    DEFAULT_SPOT_PRICE_SENSOR,
)

DEFAULT_MAP: dict[str, float] = {
    # FIX
    CONF_FIX_OBCHODNI_CENA_VT: DEFAULT_FIX_OBCHODNI_CENA_VT,
    CONF_FIX_OBCHODNI_CENA_NT: DEFAULT_FIX_OBCHODNI_CENA_NT,
    CONF_FIX_STALA_PLATBA: DEFAULT_FIX_STALA_PLATBA,
    CONF_FIX_ZA_JISTIC: DEFAULT_FIX_ZA_JISTIC,
    CONF_FIX_PROVOZ_INFRASTRUKTURY: DEFAULT_FIX_PROVOZ_INFRASTRUKTURY,
    # SPOT
    CONF_SPOT_MARZE: DEFAULT_SPOT_MARZE,
    CONF_SPOT_STALA_PLATBA: DEFAULT_SPOT_STALA_PLATBA,
    CONF_SPOT_ZA_JISTIC: DEFAULT_SPOT_ZA_JISTIC,
    CONF_SPOT_PROVOZ_INFRASTRUKTURY: DEFAULT_SPOT_PROVOZ_INFRASTRUKTURY,
    # POZE / DISTRIBUCE
    CONF_POZE: DEFAULT_POZE,
    CONF_DISTRIBUCE_VT: DEFAULT_DISTRIBUCE_VT,
    CONF_DISTRIBUCE_NT: DEFAULT_DISTRIBUCE_NT,
    CONF_DISTRIBUCE_DAN: DEFAULT_DISTRIBUCE_DAN,
    CONF_DISTRIBUCE_SLUZBY: DEFAULT_DISTRIBUCE_SLUZBY,
}


# ---------------------------
# Pomocné konverze/jednotky (MODULOVÉ FUNKCE)
# ---------------------------

def _energy_to_kwh(state: State | None) -> float | None:
    """State -> hodnota v kWh (akumulační senzor energie)."""
    if state is None or state.state in (None, "unknown", "unavailable"):
        return None
    try:
        val = float(state.state)
    except ValueError:
        return None
    unit = (state.attributes.get("unit_of_measurement") or "").lower()
    if unit in ("kwh", "kw·h", "kw*h"):
        return val
    if unit in ("wh",):
        return val / 1000.0
    # neznámá jednotka – ignoruj
    return None

def _power_to_kw(state: State | None) -> float | None:
    """State -> kW (okamžitý výkon)."""
    if state is None or state.state in (None, "unknown", "unavailable"):
        return None
    try:
        val = float(state.state)
    except ValueError:
        return None
    unit = (state.attributes.get("unit_of_measurement") or "").lower()
    if unit in ("kw",):
        return val
    if unit in ("w",):
        return val / 1000.0
    return None

def _hours_in_current_month(now: datetime) -> int:
    """Počet hodin v právě běžícím měsíci (zohlední délku měsíce)."""
    y, m = now.year, now.month
    days = monthrange(y, m)[1]
    return days * 24

def _is_low_tariff(hass: HomeAssistant, hdo_switch_entity_id: str | None) -> bool | None:
    """Zjisti, zda je aktuálně NT (True) nebo VT (False). None pokud nevíme."""
    if not hdo_switch_entity_id:
        return None
    st = hass.states.get(hdo_switch_entity_id)
    if not st or st.state in ("unknown", "unavailable", None, ""):
        return None
    return str(st.state).lower() in ("on", "true", "1")

class HDOTariffSensor(SensorEntity):
    """Sensor odvozující HDO tarif z přepínače (ON=nízký, OFF=vysoký)."""

    _attr_icon = "mdi:flash-auto"
    _attr_translation_key = "hdo_tariff"

    def __init__(self, hass: HomeAssistant, source_entity_id: str) -> None:
        self.hass = hass
        self._source_entity_id = source_entity_id
        self._unsubscribe = None
        safe_source = source_entity_id.replace(".", "_").replace(":", "_").replace("/", "_")
        self._attr_unique_id = f"{DOMAIN}_hdo_tarif_{safe_source}"
        self._state = None
        self._attrs = {}

    async def async_added_to_hass(self) -> None:
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
            self._state = "unknown"
            self._attrs = {
                ATTR_SOURCE_ENTITY_ID: self._source_entity_id,
                ATTR_SOURCE_STATE: None,
                ATTR_IS_LOW_TARIFF: None,
            }
        else:
            src_state = state_obj.state
            is_low = str(src_state).lower() in ("on", "true", "1")
            self._state = "low" if is_low else "high"
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


# ---------------------------
# Senzor: spotřeba za poslední hodinu (kWh)
# ---------------------------

class HourlyConsumptionSensor(SensorEntity):
    _attr_translation_key = "hourly_consumption"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cfg: dict) -> None:
        self.hass = hass
        self._entry = entry
        self._unique_id = f"{DOMAIN}_consumption_1h_{entry.entry_id}"
        self._attr_unique_id = self._unique_id

        # debug info
        self._dbg_mode: str | None = None                   # "energy" | "power" | None
        self._dbg_breakdown: dict[str, float] = {}          # kWh za poslední 1h per entita

        # zdroje
        self._total = cfg.get("cons_total") or ""
        self._l1 = cfg.get("cons_l1") or ""
        self._l2 = cfg.get("cons_l2") or ""
        self._l3 = cfg.get("cons_l3") or ""

        # okno posledních 60 minut – per entita
        self._energy_samples_by_ent: dict[str, deque[tuple[datetime, float]]] = defaultdict(deque)
        self._power_samples_by_ent: dict[str, deque[tuple[datetime, float]]] = defaultdict(deque)
        self._unsubs: list[callable] = []

    @property
    def unique_id(self) -> str:
        return self._unique_id

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _trim(self):
        cutoff = self._now() - timedelta(hours=1)
        for dq in self._energy_samples_by_ent.values():
            while dq and dq[0][0] < cutoff:
                dq.popleft()
        for dq in self._power_samples_by_ent.values():
            while dq and dq[0][0] < cutoff:
                dq.popleft()

    def _sample_energy_for_ent(self, ent_id: str) -> None:
        st = self.hass.states.get(ent_id)
        val = _energy_to_kwh(st)
        if val is not None:
            self._energy_samples_by_ent[ent_id].append((self._now(), val))

    def _sample_power_for_ent(self, ent_id: str) -> None:
        st = self.hass.states.get(ent_id)
        val = _power_to_kw(st)
        if val is not None:
            self._power_samples_by_ent[ent_id].append((self._now(), val))

    @callback
    def _on_source_change(self, _event):
        self._recompute()
        self.async_write_ha_state()

    def _delta_1h_energy(self) -> tuple[float, dict[str, float]]:
        total = 0.0
        per_ent: dict[str, float] = {}
        for ent_id, dq in self._energy_samples_by_ent.items():
            if len(dq) >= 2:
                first = dq[0][1]
                last = dq[-1][1]
                d = max(0.0, last - first)
                per_ent[ent_id] = d
                total += d
        return total, per_ent

    def _integrate_1h_power(self) -> tuple[float, dict[str, float]]:
        total = 0.0
        per_ent: dict[str, float] = {}
        for ent_id, dq in self._power_samples_by_ent.items():
            if len(dq) < 2:
                continue
            acc = 0.0
            prev_t, prev_p = dq[0]
            for t, p in list(dq)[1:]:
                dt_h = (t - prev_t).total_seconds() / 3600.0
                acc += (prev_p + p) * 0.5 * dt_h
                prev_t, prev_p = t, p
            acc = max(0.0, acc)
            per_ent[ent_id] = acc
            total += acc
        return total, per_ent

    def _recompute(self):
        # 1) přidej nové vzorky (total nebo fáze)
        if self._total:
            self._sample_energy_for_ent(self._total)
        for ent in (self._l1, self._l2, self._l3):
            if not ent:
                continue
            # Zkus nejdřív ENERGY; pokud není, dej POWER
            if _energy_to_kwh(self.hass.states.get(ent)) is not None:
                self._sample_energy_for_ent(ent)
            elif _power_to_kw(self.hass.states.get(ent)) is not None:
                self._sample_power_for_ent(ent)

        # 2) ořízni okna na poslední hodinu
        self._trim()

        # 3) výsledná 1h spotřeba
        val_energy, per_energy = self._delta_1h_energy()
        if val_energy > 0:
            self._dbg_mode = "energy"
            self._dbg_breakdown = per_energy
            val = val_energy
        else:
            val_power, per_power = self._integrate_1h_power()
            self._dbg_mode = "power"
            self._dbg_breakdown = per_power
            val = val_power

        self._attr_native_value = round(val, 6)

    # Export debug dat pro cenový senzor
    def get_debug_data(self) -> dict:
        return {
            "mode": self._dbg_mode,
            "total_kwh": float(self._attr_native_value or 0.0),
            "per_entity_kwh": dict(self._dbg_breakdown),
        }

    async def async_added_to_hass(self) -> None:
        self._recompute()
        ents = [e for e in [self._total, self._l1, self._l2, self._l3] if e]
        if ents:
            self._unsubs.append(async_track_state_change_event(self.hass, ents, self._on_source_change))

    async def async_will_remove_from_hass(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()

class _DailyTariffEnergySensor(SensorEntity, RestoreEntity):
    """Denní akumulace spotřeby (kWh) dle tarifu (VT/NT). Reset o půlnoci."""

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL  # v rámci dne roste, o půlnoci reset

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cons_sensor: "HourlyConsumptionSensor", hdo_switch: str | None, want_nt: bool) -> None:
        self.hass = hass
        self._entry = entry
        self._cons = cons_sensor
        self._hdo_switch = hdo_switch
        self._want_nt = want_nt  # True=NT, False=VT

        tag = "nt" if want_nt else "vt"
        self._attr_unique_id = f"{DOMAIN}_daily_energy_{tag}_{entry.entry_id}"

        self._unsubs: list[callable] = []
        self._value: float = 0.0
        self._day_key: str | None = None   # "YYYY-MM-DD"
        self._last_closed_total: float | None = None

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _cur_day_key(self) -> str:
        return self._now().strftime("%Y-%m-%d")

    def _cons_1h(self) -> float:
        try:
            return float(self._cons.native_value or 0.0)
        except Exception:
            return 0.0

    async def async_added_to_hass(self) -> None:
        # obnov poslední stav
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable", ""):
            try:
                self._value = float(last.state)
            except Exception:
                self._value = 0.0
        if last:
            self._day_key = last.attributes.get("day_key") or None
            lct = last.attributes.get("last_closed_total")
            self._last_closed_total = float(lct) if isinstance(lct, (int, float)) else None

        # tick: každou celou hodinu přičti spotřebu, pokud odpovídá tarifu
        self._unsubs.append(async_track_time_change(self.hass, self._on_hour_tick, minute=0, second=12))
        # plus malý půlnoční „pojistný“ tick (kdyby HA přes půlnoc nespal)
        self._unsubs.append(async_track_time_change(self.hass, self._on_midnight_tick, hour=0, minute=0, second=30))

        if not self._day_key:
            self._day_key = self._cur_day_key()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()

    @callback
    def _on_midnight_tick(self, _now) -> None:
        # o půlnoci uzavři předchozí den (pokud by _on_hour_tick zrovna neběžel)
        today = self._cur_day_key()
        if self._day_key and self._day_key != today:
            self._last_closed_total = self._value
            self._value = 0.0
            self._day_key = today
            self.async_write_ha_state()

    @callback
    def _on_hour_tick(self, _now) -> None:
        today = self._cur_day_key()
        # změna dne? uzavři a reset
        if self._day_key and self._day_key != today:
            self._last_closed_total = self._value
            self._value = 0.0
            self._day_key = today

        # přičtení dle aktuálního tarifu
        is_nt = _is_low_tariff(self.hass, self._hdo_switch)
        use_bucket = (is_nt is True) if self._want_nt else (is_nt is False)
        if use_bucket:
            self._value = round(self._value + self._cons_1h(), 6)

        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return self._value

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "tarif": "NT" if self._want_nt else "VT",
            "day_key": self._day_key,
            "last_closed_total": self._last_closed_total,
            "source_consumption_entity": getattr(self._cons, "entity_id", None),
            "hdo_switch": self._hdo_switch,
        }


class DailyEnergyVTSensor(_DailyTariffEnergySensor):
    _attr_translation_key = "daily_energy_vt"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cons_sensor: "HourlyConsumptionSensor", hdo_switch: str | None) -> None:
        super().__init__(hass, entry, cons_sensor, hdo_switch, want_nt=False)


class DailyEnergyNTSensor(_DailyTariffEnergySensor):
    _attr_translation_key = "daily_energy_nt"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cons_sensor: "HourlyConsumptionSensor", hdo_switch: str | None) -> None:
        super().__init__(hass, entry, cons_sensor, hdo_switch, want_nt=True)

# ---------------------------
# Senzor: cena za poslední hodinu (CZK)
# ---------------------------

class SpotHourlyCostSensor(SensorEntity):
    _attr_translation_key = "spot_cost_hourly"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "CZK"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cfg: dict, cons_sensor: HourlyConsumptionSensor) -> None:
        self.hass = hass
        self._entry = entry
        self._unique_id = f"{DOMAIN}_spot_cost_1h_{entry.entry_id}"
        self._attr_unique_id = self._unique_id

        self._cons_entity = cons_sensor
        self._price_entity_id = cfg.get("spot_price_sensor") or DEFAULT_SPOT_PRICE_SENSOR
        self._unsubs: list[callable] = []

        # logování
        # po přiřazení self._price_entity_id
        LOGGER.debug(
            "Entry options (live) for %s: %s | spot_price_sensor=%s",
            self.__class__.__name__, dict(entry.options), self._price_entity_id
        )

    @property
    def unique_id(self) -> str:
        return self._unique_id

    def _opt(self, key: str, default: float | None = None) -> float:
        """Čti aktuální hodnotu z entry.options → entry.data → DEFAULT_MAP."""
        if default is None:
            default = DEFAULT_MAP.get(key, 0.0)
        # 1) aktuální options
        if key in self._entry.options:
            try:
                return float(self._entry.options[key])
            except Exception:
                return float(default or 0.0)
        # 2) původní data z config flow
        if key in self._entry.data:
            try:
                return float(self._entry.data[key])
            except Exception:
                return float(default or 0.0)
        # 3) fallback
        return float(default or 0.0)

    def _price_kwh(self) -> float:
        st = self.hass.states.get(self._price_entity_id)
        if not st or st.state in ("unknown", "unavailable", None, ""):
            return 0.0
        try:
            return float(st.state)
        except Exception:
            return 0.0

    def _cons_kwh(self) -> float:
        val = self._cons_entity.native_value
        try:
            return float(val or 0.0)
        except Exception:
            return 0.0

    def _recompute(self):
        # načtení hodnot
        spot = self._price_kwh()
        marze = self._opt(CONF_SPOT_MARZE, 0.0)
        distribuce_vt = self._opt(CONF_DISTRIBUCE_VT, 0.0)
        distribuce_dan = self._opt(CONF_DISTRIBUCE_DAN, 0.0)
        distribuce_sluzby = self._opt(CONF_DISTRIBUCE_SLUZBY, 0.0)
        poze = self._opt(CONF_POZE, 0.0)
        cons = self._cons_kwh()

        # výpočet
        unit_kc_per_kwh = (spot + marze) + distribuce_vt + (distribuce_dan + distribuce_sluzby) + poze
        result_kc = unit_kc_per_kwh * cons
        self._attr_native_value = round(result_kc, 6)

        # jemný debug při každém přepočtu
        LOGGER.debug(
            "[spot_cost_1h] spot=%.6f, marze=%.6f, dist_vt=%.6f, dist_dan=%.6f, dist_sluzby=%.6f, poze=%.6f, cons_1h=%.6f => unit=%.6f Kč/kWh, result=%.6f Kč",
            spot, marze, distribuce_vt, distribuce_dan, distribuce_sluzby, poze, cons, unit_kc_per_kwh, result_kc
        )

        # podklady pro hodinový report
        self._last_debug_payload = {
            "spot": spot,
            "marze": marze,
            "distribuce_vt": distribuce_vt,
            "distribuce_dan": distribuce_dan,
            "distribuce_sluzby": distribuce_sluzby,
            "poze": poze,
            "cons_1h": cons,
            "unit": unit_kc_per_kwh,
            "result": result_kc,
            "cons_breakdown": getattr(self._cons_entity, "get_debug_data", lambda: {})(),
        }

    async def async_added_to_hass(self) -> None:
        # změny spotové ceny
        self._unsubs.append(
            async_track_state_change_event(self.hass, [self._price_entity_id], self._on_change)
        )
        self._last_debug_payload: dict | None = None

        # 1× za hodinu (na celé) souhrnný report do logu
        self._unsubs.append(
            async_track_time_change(self.hass, self._hourly_report, minute=0, second=5)
        )
        self._recompute()

    @callback
    def _on_change(self, *_):
        self._recompute()
        self.async_write_ha_state()

    @callback
    def _hourly_report(self, now):
        """Hodinový souhrn do logu: dosazení do vzorce + výsledek."""
        self._recompute()
        payload = self._last_debug_payload or {}

        spot = payload.get("spot", 0.0)
        marze = payload.get("marze", 0.0)
        dv = payload.get("distribuce_vt", 0.0)
        dd = payload.get("distribuce_dan", 0.0)
        ds = payload.get("distribuce_sluzby", 0.0)
        poze = payload.get("poze", 0.0)
        cons = payload.get("cons_1h", 0.0)
        unit = payload.get("unit", 0.0)
        result = payload.get("result", 0.0)
        cons_dbg = payload.get("cons_breakdown", {})

        formula = f"(({spot:.6f}+{marze:.6f}) + {dv:.6f} + ({dd:.6f}+{ds:.6f}) + {poze:.6f}) * {cons:.6f} = {result:.6f} Kč"

        LOGGER.debug(
            "[spot_cost_1h][%s] VZOREC: %s | jednotkova_cena=%.6f Kč/kWh | spotreba_1h=%.6f kWh | rozpad_spotreby=%s",
            now.isoformat(), formula, unit, cons, cons_dbg,
        )
        LOGGER.info(
            "[spot_cost_1h][%s] Cena za posledni hodinu: %.6f Kč (unit=%.6f Kč/kWh, spotreba=%.6f kWh)",
            now.isoformat(), result, unit, cons
        )

    async def async_will_remove_from_hass(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()

class FixHourlyCostSensor(SensorEntity):
    _attr_translation_key = "fix_cost_hourly"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "CZK"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cfg: dict, cons_sensor: HourlyConsumptionSensor) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_fix_cost_1h_{entry.entry_id}"

        self._cons_entity = cons_sensor
        self._hdo_switch = cfg.get("source_entity_id")  # HDO přepínač

        self._unsubs: list[callable] = []
        self._last_debug_payload: dict | None = None

        # DEBUG
        LOGGER.debug(
            "Entry options (live) for %s: %s | hdo_switch=%s",
            self.__class__.__name__, dict(entry.options), self._hdo_switch
        )

    def _opt(self, key: str, default: float | None = None) -> float:
        """Čti aktuální hodnotu z entry.options → entry.data → DEFAULT_MAP."""
        if default is None:
            default = DEFAULT_MAP.get(key, 0.0)

        # 1) aktuální options
        if key in self._entry.options:
            try:
                return float(self._entry.options[key])
            except Exception:
                LOGGER.debug(
                    "Chyba v získání ceny - krok 1 - aktuální options",
                    exc_info=True,
                )
                return float(default or 0.0)

        # 2) původní data z config flow
        if key in self._entry.data:
            try:
                return float(self._entry.data[key])
            except Exception:
                LOGGER.debug(
                    "Chyba v získání ceny - krok 2 - původní data z config flow",
                    exc_info=True,
                )
                return float(default or 0.0)

        # 3) fallback
        LOGGER.debug("Chyba v získání ceny - krok 3 - fallback")
        return float(default or 0.0)

    def _cons_kwh(self) -> float:
        try:
            return float(self._cons_entity.native_value or 0.0)
        except Exception:
            return 0.0

    def _hourly_fixed_share(self) -> float:
        """Rozpočítaná měsíční paušální částka na 1 hodinu aktuálního měsíce."""
        now = datetime.now(timezone.utc)
        hours = _hours_in_current_month(now)
        total_monthly = (
            self._opt(CONF_FIX_STALA_PLATBA, 0.0)
            + self._opt(CONF_FIX_ZA_JISTIC, 0.0)
            + self._opt(CONF_FIX_PROVOZ_INFRASTRUKTURY, 0.0)
        )
        return total_monthly / hours if hours > 0 else 0.0

    def _unit_price_kc_per_kwh(self) -> tuple[float, dict]:
        """Jednotková cena za kWh dle aktuálního tarifu (bez paušálů). Vrací (unit_price, debug dict)."""
        is_nt = _is_low_tariff(self.hass, self._hdo_switch)
        # bezpečný default – když nevíme, použij VT
        use_nt = (is_nt is True)

        if use_nt:
            energy = self._opt(CONF_FIX_OBCHODNI_CENA_NT, 0.0)
            distrib = self._opt(CONF_DISTRIBUCE_NT, 0.0)
            tarif = "NT"
        else:
            energy = self._opt(CONF_FIX_OBCHODNI_CENA_VT, 0.0)
            distrib = self._opt(CONF_DISTRIBUCE_VT, 0.0)
            tarif = "VT"

        distrib_common = self._opt(CONF_DISTRIBUCE_DAN, 0.0) + self._opt(CONF_DISTRIBUCE_SLUZBY, 0.0)
        poze = self._opt(CONF_POZE, 0.0)

        unit = energy + distrib + distrib_common + poze

        dbg = {
            "tarif": tarif if is_nt is not None else "VT (fallback, HDO neznámé)",
            "fix_energy": energy,
            "distrib_tarif": distrib,
            "distrib_common": distrib_common,
            "poze": poze,
        }
        return unit, dbg

    def _recompute(self):
        cons = self._cons_kwh()
        unit, dbg = self._unit_price_kc_per_kwh()
        hourly_fixed = self._hourly_fixed_share()

        result_kc = unit * cons + hourly_fixed
        self._attr_native_value = round(result_kc, 6)

        # DEBUG detail
        LOGGER.debug(
            "[fix_cost_1h] unit=%.6f Kč/kWh (tarif=%s, energy=%.6f, dist_t=%.6f, dist_c=%.6f, poze=%.6f); "
            "cons_1h=%.6f kWh; hourly_fixed=%.6f Kč => result=%.6f Kč",
            unit,
            dbg["tarif"],
            dbg["fix_energy"], dbg["distrib_tarif"], dbg["distrib_common"], dbg["poze"],
            cons, hourly_fixed, result_kc,
        )

        self._last_debug_payload = {
            "unit": unit,
            "tarif": dbg["tarif"],
            "fix_energy": dbg["fix_energy"],
            "distrib_tarif": dbg["distrib_tarif"],
            "distrib_common": dbg["distrib_common"],
            "poze": dbg["poze"],
            "cons_1h": cons,
            "hourly_fixed": hourly_fixed,
            "result": result_kc,
        }

    async def async_added_to_hass(self) -> None:
        # přepočítej při změně HDO přepínače i kdykoli přeteče hodina (kvůli paušálům)
        if self._hdo_switch:
            self._unsubs.append(
                async_track_state_change_event(self.hass, [self._hdo_switch], self._on_change)
            )
        # každou celou hodinu proveď přepočet a zapíš „report“
        self._unsubs.append(async_track_time_change(self.hass, self._hourly_report, minute=0, second=7))
        self._recompute()

    @callback
    def _on_change(self, *_):
        self._recompute()
        self.async_write_ha_state()

    @callback
    def _hourly_report(self, now):
        self._recompute()
        p = self._last_debug_payload or {}
        unit = p.get("unit", 0.0)
        cons = p.get("cons_1h", 0.0)
        hf = p.get("hourly_fixed", 0.0)
        res = p.get("result", 0.0)
        tarif = p.get("tarif", "?")
        fe = p.get("fix_energy", 0.0)
        dt = p.get("distrib_tarif", 0.0)
        dc = p.get("distrib_common", 0.0)
        poze = p.get("poze", 0.0)

        formula = f"([{tarif}] ({fe:.6f}+{dt:.6f}+{dc:.6f}+{poze:.6f}) * {cons:.6f}) + hourly_fixed({hf:.6f}) = {res:.6f} Kč"
        LOGGER.debug("[fix_cost_1h][%s] VZOREC: %s | unit=%.6f Kč/kWh | cons=%.6f kWh | hourly_fixed=%.6f Kč",
                     now.isoformat(), formula, unit, cons, hf)
        LOGGER.info("[fix_cost_1h][%s] Cena za posledni hodinu (fix): %.6f Kč (unit=%.6f, cons=%.6f kWh, paušál/h=%.6f)",
                    now.isoformat(), res, unit, cons, hf)

class _BaseAccumCostSensor(SensorEntity, RestoreEntity):
    """Základ pro denní/měsíční akumulaci hodinové ceny."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "CZK"
    _attr_state_class = SensorStateClass.TOTAL  # v rámci období roste, na hranici období se vynuluje

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cost_sensor: "SpotHourlyCostSensor", period: str) -> None:
        assert period in ("day", "month")
        self.hass = hass
        self._entry = entry
        self._cost_sensor = cost_sensor
        self._period = period
        self._unsubs: list[callable] = []

        self._value = 0.0
        self._period_key: str | None = None   # "YYYY-MM-DD" nebo "YYYY-MM"
        self._last_closed_total: float | None = None  # poslední uzavřené období (pro info do atributu)

    # --- pomocné ---
    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _current_key(self) -> str:
        now = self._now()
        if self._period == "day":
            return now.strftime("%Y-%m-%d")
        return now.strftime("%Y-%m")

    def _get_latest_hour_cost(self) -> float:
        """Vezmi aktuální hodinovou cenu z cenového senzoru (vždy pro okno, které právě skončilo)."""
        # přepočítej, ať je čerstvá
        self._cost_sensor._recompute()  # vědomě voláme interní přepočet
        val = self._cost_sensor.native_value
        try:
            return float(val or 0.0)
        except Exception:
            return 0.0

    # --- HA lifecycle ---
    async def async_added_to_hass(self) -> None:
        # obnov stav po restartu
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable", ""):
            try:
                self._value = float(last.state)
            except Exception:
                self._value = 0.0
        if last:
            self._period_key = last.attributes.get("period_key") or None
            lct = last.attributes.get("last_closed_total")
            self._last_closed_total = float(lct) if isinstance(lct, (int, float)) else None

        # každou hodinu (na celé) přičti hodinovou cenu
        self._unsubs.append(async_track_time_change(self.hass, self._on_hour_tick, minute=0, second=10))

        # na startu inicializuj period key
        if not self._period_key:
            self._period_key = self._current_key()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()

    @callback
    def _on_hour_tick(self, _now) -> None:
        cur_key = self._current_key()
        # Na hranici období ulož uzavřený součet a vynuluj
        if self._period_key and cur_key != self._period_key:
            # uzavíráme minulé období
            self._last_closed_total = self._value
            self._value = 0.0
            self._period_key = cur_key

        # Přičti cenu za předchozí hodinu
        self._value = round(self._value + self._get_latest_hour_cost(), 6)
        self.async_write_ha_state()

    # --- hodnoty/atributy ---
    @property
    def native_value(self) -> float:
        return self._value

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "period": self._period,                 # "day" / "month"
            "period_key": self._period_key,         # např. "2025-09-07" nebo "2025-09"
            "last_closed_total": self._last_closed_total,  # kolik stál předchozí den/měsíc
        }


class DailySpotCostSensor(_BaseAccumCostSensor):
    _attr_translation_key = "spot_cost_daily"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cost_sensor: "SpotHourlyCostSensor") -> None:
        super().__init__(hass, entry, cost_sensor, period="day")
        self._attr_unique_id = f"{DOMAIN}_spot_cost_den_{entry.entry_id}"

class DailyFixCostSensor(_BaseAccumCostSensor):
    _attr_translation_key = "fix_cost_daily"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cost_sensor: "FixHourlyCostSensor") -> None:
        super().__init__(hass, entry, cost_sensor, period="day")
        self._attr_unique_id = f"{DOMAIN}_fix_cost_den_{entry.entry_id}"

class MonthlySpotCostSensor(_BaseAccumCostSensor):
    _attr_translation_key = "spot_cost_monthly"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cost_sensor: "SpotHourlyCostSensor") -> None:
        super().__init__(hass, entry, cost_sensor, period="month")
        self._attr_unique_id = f"{DOMAIN}_spot_cost_mesic_{entry.entry_id}"

class MonthlyFixCostSensor(_BaseAccumCostSensor):
    _attr_translation_key = "fix_cost_monthly"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cost_sensor: "FixHourlyCostSensor") -> None:
        super().__init__(hass, entry, cost_sensor, period="month")
        self._attr_unique_id = f"{DOMAIN}_fix_cost_mesic_{entry.entry_id}"

# ---------------------------
# Registrace entit (MODULOVÁ!)
# ---------------------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    cfg = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    # 1) HDO – zdrojový přepínač
    source_entity_id = cfg.get("source_entity_id")
    if source_entity_id:
        entities.append(HDOTariffSensor(hass, source_entity_id))

    # 2) Spotřeba poslední hodiny
    cons = HourlyConsumptionSensor(hass, entry, cfg)
    entities.append(cons)

    # 3) Cena (spot) poslední hodiny + denní/měsíční součty
    cost_spot = SpotHourlyCostSensor(hass, entry, cfg, cons)
    entities.append(cost_spot)
    entities.append(DailySpotCostSensor(hass, entry, cost_spot))
    entities.append(MonthlySpotCostSensor(hass, entry, cost_spot))

    # 4) Cena (fix) poslední hodiny + denní/měsíční součty  ← NOVÉ
    cost_fix = FixHourlyCostSensor(hass, entry, cfg, cons)
    entities.append(cost_fix)
    entities.append(DailyFixCostSensor(hass, entry, cost_fix))
    entities.append(MonthlyFixCostSensor(hass, entry, cost_fix))

    # 5) denní spotřeba VT/NT <<<
    entities.append(DailyEnergyVTSensor(hass, entry, cons, source_entity_id))
    entities.append(DailyEnergyNTSensor(hass, entry, cons, source_entity_id))

    async_add_entities(entities, True)
