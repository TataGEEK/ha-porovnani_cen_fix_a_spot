# custom_components/porovnani_cen_fix_a_spot/config_flow.py
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN, DEFAULT_SOURCE_ENTITY_ID,
    # --- ceny VT/NT ---
    CONF_FIX_OBCHODNI_CENA_VT, CONF_FIX_OBCHODNI_CENA_NT,
    DEFAULT_FIX_OBCHODNI_CENA_VT, DEFAULT_FIX_OBCHODNI_CENA_NT,
    # --- FIX konstanty ---
    CONF_FIX_STALA_PLATBA, CONF_FIX_ZA_JISTIC, CONF_FIX_PROVOZ_INFRASTRUKTURY,
    DEFAULT_FIX_STALA_PLATBA, DEFAULT_FIX_ZA_JISTIC, DEFAULT_FIX_PROVOZ_INFRASTRUKTURY,
    # --- SPOT konstanty ---
    CONF_SPOT_MARZE, CONF_SPOT_STALA_PLATBA, CONF_SPOT_ZA_JISTIC, CONF_SPOT_PROVOZ_INFRASTRUKTURY,
    DEFAULT_SPOT_MARZE, DEFAULT_SPOT_STALA_PLATBA, DEFAULT_SPOT_ZA_JISTIC, DEFAULT_SPOT_PROVOZ_INFRASTRUKTURY,
    # --- POZE ---
    CONF_POZE, DEFAULT_POZE,
    # --- DISTRIBUCE ---
    CONF_DISTRIBUCE_VT, CONF_DISTRIBUCE_NT, CONF_DISTRIBUCE_DAN, CONF_DISTRIBUCE_SLUZBY,
    DEFAULT_DISTRIBUCE_VT, DEFAULT_DISTRIBUCE_NT, DEFAULT_DISTRIBUCE_DAN, DEFAULT_DISTRIBUCE_SLUZBY,
    # --- senzory spotřeby energie domácnosti (celková nebo po fázích)
    CONF_CONS_TOTAL_ENERGY, CONF_CONS_PHASE1, CONF_CONS_PHASE2, CONF_CONS_PHASE3,
    DEFAULT_CONS_TOTAL_ENERGY, DEFAULT_CONS_PHASE1, DEFAULT_CONS_PHASE2, DEFAULT_CONS_PHASE3,
    # --- profil
    CONF_PROFILE_NAME, DEFAULT_PROFILE_NAME,
)


# Úvodní konfigurace (výběr HDO + spotřeba)
DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_ENTITY_ID, default=DEFAULT_SOURCE_ENTITY_ID):
        selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["switch"])
        ),

    # Spotřeba – A) jeden celkový senzor energie (doporučeno)
    vol.Optional(CONF_CONS_TOTAL_ENERGY):
        selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor"],
                device_class=["energy"]  # kWh/Wh
            )
        ),

    # Spotřeba – B) per-fáze (energy nebo power)
    vol.Optional(CONF_CONS_PHASE1):
        selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor"], device_class=["energy", "power"]
            )
        ),
    vol.Optional(CONF_CONS_PHASE2):
        selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor"], device_class=["energy", "power"]
            )
        ),
    vol.Optional(CONF_CONS_PHASE3):
        selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor"], device_class=["energy", "power"]
            )
        ),
    vol.Optional(CONF_PROFILE_NAME):
        selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
            errors: dict[str, str] = {}

            if user_input is not None:
                total = (user_input.get(CONF_CONS_TOTAL_ENERGY) or "").strip()
                l1 = (user_input.get(CONF_CONS_PHASE1) or "").strip()
                l2 = (user_input.get(CONF_CONS_PHASE2) or "").strip()
                l3 = (user_input.get(CONF_CONS_PHASE3) or "").strip()

                if not total and not l1:
                    errors["base"] = "consumption_missing"
                else:
                    name = (user_input.get(CONF_PROFILE_NAME) or "").strip() or "Porovnání cen"
                    return self.async_create_entry(
                        title=name,
                        data={
                            "source_entity_id": user_input[CONF_ENTITY_ID],
                            CONF_CONS_TOTAL_ENERGY: total,
                            CONF_CONS_PHASE1: l1,
                            CONF_CONS_PHASE2: l2,
                            CONF_CONS_PHASE3: l3,
                            CONF_PROFILE_NAME: name,
                        },
                    )

            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    # Hlavní menu se 4 bloky
    async def async_step_init(self, user_input=None):
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(
            step_id="menu",
            menu_options=["fix", "spot", "distribuce", "poze", "profil"]
        )

    # ==== FIX: jedna stránka s obchodní cenou VT/NT (a později sem může přijít i paušál) ====
    async def async_step_fix(self, user_input=None):
        opts = self.config_entry.options
        cur_vt = opts.get(CONF_FIX_OBCHODNI_CENA_VT, DEFAULT_FIX_OBCHODNI_CENA_VT)
        cur_nt = opts.get(CONF_FIX_OBCHODNI_CENA_NT, DEFAULT_FIX_OBCHODNI_CENA_NT)

        cur_stala   = opts.get(CONF_FIX_STALA_PLATBA, DEFAULT_FIX_STALA_PLATBA)
        cur_jistic  = opts.get(CONF_FIX_ZA_JISTIC, DEFAULT_FIX_ZA_JISTIC)
        cur_infra   = opts.get(CONF_FIX_PROVOZ_INFRASTRUKTURY, DEFAULT_FIX_PROVOZ_INFRASTRUKTURY)

        schema = vol.Schema({
            vol.Required(CONF_FIX_OBCHODNI_CENA_VT, default=cur_vt):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step=0.001, mode="box",
                        unit_of_measurement="Kč/kWh"
                    )
                ),
            vol.Required(CONF_FIX_OBCHODNI_CENA_NT, default=cur_nt):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step=0.001, mode="box",
                        unit_of_measurement="Kč/kWh"
                    )
                ),
            # Paušály [Kč/měs]
            vol.Required(CONF_FIX_STALA_PLATBA, default=cur_stala):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, step=0.01, mode="box", unit_of_measurement="Kč/měs")
                ),
            vol.Required(CONF_FIX_ZA_JISTIC, default=cur_jistic):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, step=0.01, mode="box", unit_of_measurement="Kč/měs")
                ),
            vol.Required(CONF_FIX_PROVOZ_INFRASTRUKTURY, default=cur_infra):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, step=0.01, mode="box", unit_of_measurement="Kč/měs")
                ),
        })

        if user_input is not None:
            new_opts = dict(self.config_entry.options)
            new_opts[CONF_FIX_OBCHODNI_CENA_VT] = float(user_input[CONF_FIX_OBCHODNI_CENA_VT])
            new_opts[CONF_FIX_OBCHODNI_CENA_NT] = float(user_input[CONF_FIX_OBCHODNI_CENA_NT])
            
            new_opts[CONF_FIX_STALA_PLATBA] = float(user_input[CONF_FIX_STALA_PLATBA])
            new_opts[CONF_FIX_ZA_JISTIC] = float(user_input[CONF_FIX_ZA_JISTIC])
            new_opts[CONF_FIX_PROVOZ_INFRASTRUKTURY] = float(user_input[CONF_FIX_PROVOZ_INFRASTRUKTURY])


            return self.async_create_entry(title="", data=new_opts)

        return self.async_show_form(step_id="fix", data_schema=schema)

    async def async_step_spot(self, user_input=None):
        opts = self.config_entry.options

        cur_marze = opts.get(CONF_SPOT_MARZE, DEFAULT_SPOT_MARZE)
        cur_stala = opts.get(CONF_SPOT_STALA_PLATBA, DEFAULT_SPOT_STALA_PLATBA)
        cur_jistic = opts.get(CONF_SPOT_ZA_JISTIC, DEFAULT_SPOT_ZA_JISTIC)
        cur_infra = opts.get(CONF_SPOT_PROVOZ_INFRASTRUKTURY, DEFAULT_SPOT_PROVOZ_INFRASTRUKTURY)

        schema = vol.Schema({
            # Marže [Kč/kWh]
            vol.Required(CONF_SPOT_MARZE, default=cur_marze):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, step=0.001, mode="box", unit_of_measurement="Kč/kWh")
                ),
            # Paušály [Kč/měs]
            vol.Required(CONF_SPOT_STALA_PLATBA, default=cur_stala):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, step=0.01, mode="box", unit_of_measurement="Kč/měs")
                ),
            vol.Required(CONF_SPOT_ZA_JISTIC, default=cur_jistic):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, step=0.01, mode="box", unit_of_measurement="Kč/měs")
                ),
            vol.Required(CONF_SPOT_PROVOZ_INFRASTRUKTURY, default=cur_infra):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, step=0.01, mode="box", unit_of_measurement="Kč/měs")
                ),
        })

        if user_input is not None:
            new_opts = dict(self.config_entry.options)
            new_opts[CONF_SPOT_MARZE] = float(user_input[CONF_SPOT_MARZE])
            new_opts[CONF_SPOT_STALA_PLATBA] = float(user_input[CONF_SPOT_STALA_PLATBA])
            new_opts[CONF_SPOT_ZA_JISTIC] = float(user_input[CONF_SPOT_ZA_JISTIC])
            new_opts[CONF_SPOT_PROVOZ_INFRASTRUKTURY] = float(user_input[CONF_SPOT_PROVOZ_INFRASTRUKTURY])
            return self.async_create_entry(title="", data=new_opts)

        return self.async_show_form(step_id="spot", data_schema=schema)

    async def async_step_poze(self, user_input=None):
        opts = self.config_entry.options
        cur_poze = opts.get(CONF_POZE, DEFAULT_POZE)

        schema = vol.Schema({
            vol.Required(CONF_POZE, default=cur_poze):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step=0.001, mode="box", unit_of_measurement="Kč/kWh"
                    )
                ),
        })

        if user_input is not None:
            new_opts = dict(self.config_entry.options)
            new_opts[CONF_POZE] = float(user_input[CONF_POZE])
            return self.async_create_entry(title="", data=new_opts)

        return self.async_show_form(step_id="poze", data_schema=schema)

    async def async_step_distribuce(self, user_input=None):
        opts = self.config_entry.options
        cur_vt = opts.get(CONF_DISTRIBUCE_VT, DEFAULT_DISTRIBUCE_VT)
        cur_nt = opts.get(CONF_DISTRIBUCE_NT, DEFAULT_DISTRIBUCE_NT)
        cur_dan = opts.get(CONF_DISTRIBUCE_DAN, DEFAULT_DISTRIBUCE_DAN)
        cur_sluzby = opts.get(CONF_DISTRIBUCE_SLUZBY, DEFAULT_DISTRIBUCE_SLUZBY)

        schema = vol.Schema({
            vol.Required(CONF_DISTRIBUCE_VT, default=cur_vt):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step=0.001, mode="box", unit_of_measurement="Kč/kWh"
                    )
                ),
            vol.Required(CONF_DISTRIBUCE_NT, default=cur_nt):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step=0.001, mode="box", unit_of_measurement="Kč/kWh"
                    )
                ),
            vol.Required(CONF_DISTRIBUCE_DAN, default=cur_dan):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step=0.001, mode="box", unit_of_measurement="Kč/kWh"
                    )
                ),
            vol.Required(CONF_DISTRIBUCE_SLUZBY, default=cur_sluzby):
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, step=0.001, mode="box", unit_of_measurement="Kč/kWh"
                    )
                ),
        })

        if user_input is not None:
            new_opts = dict(self.config_entry.options)
            new_opts[CONF_DISTRIBUCE_VT] = float(user_input[CONF_DISTRIBUCE_VT])
            new_opts[CONF_DISTRIBUCE_NT] = float(user_input[CONF_DISTRIBUCE_NT])
            new_opts[CONF_DISTRIBUCE_DAN] = float(user_input[CONF_DISTRIBUCE_DAN])
            new_opts[CONF_DISTRIBUCE_SLUZBY] = float(user_input[CONF_DISTRIBUCE_SLUZBY])
            return self.async_create_entry(title="", data=new_opts)

        return self.async_show_form(step_id="distribuce", data_schema=schema)

    async def async_step_profil(self, user_input=None):
        cur = self.config_entry.options.get(
            CONF_PROFILE_NAME,
            self.config_entry.data.get(CONF_PROFILE_NAME, DEFAULT_PROFILE_NAME),
        )

        schema = vol.Schema({
            vol.Optional(CONF_PROFILE_NAME, default=cur):
                selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT))
        })

        if user_input is not None:
            new_opts = dict(self.config_entry.options)
            new_opts[CONF_PROFILE_NAME] = (user_input.get(CONF_PROFILE_NAME) or "").strip() or DEFAULT_PROFILE_NAME
            return self.async_create_entry(title="", data=new_opts)

        return self.async_show_form(step_id="profil", data_schema=schema)
