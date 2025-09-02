from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN, DEFAULT_SOURCE_ENTITY_ID

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_ENTITY_ID, default=DEFAULT_SOURCE_ENTITY_ID):
        selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["switch"])  # jen přepínače
        )
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            # selector už zajistí, že jde o switch.* – není nutné ručně kontrolovat
            return self.async_create_entry(
                title="Porovnání cen (HDO)",
                data={"source_entity_id": user_input[CONF_ENTITY_ID]},
            )
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={"source_entity_id": user_input[CONF_ENTITY_ID]},
            )

        current = self.config_entry.options.get(
            "source_entity_id",
            self.config_entry.data.get("source_entity_id", DEFAULT_SOURCE_ENTITY_ID),
        )

        schema = vol.Schema({
            vol.Required(CONF_ENTITY_ID, default=current):
                selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch"])
                )
        })
        return self.async_show_form(step_id="user", data_schema=schema)
