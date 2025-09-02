from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import callback

from .const import DOMAIN, DEFAULT_SOURCE_ENTITY_ID


DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_ENTITY_ID, default=DEFAULT_SOURCE_ENTITY_ID): str}
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input.get(CONF_ENTITY_ID)
            if entity_id and entity_id.startswith("switch."):
                return self.async_create_entry(
                    title="Porovnání cen (HDO)",
                    data={"source_entity_id": entity_id},
                )
            errors["base"] = "invalid_entity"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

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
        schema = vol.Schema({vol.Required(CONF_ENTITY_ID, default=current): str})
        return self.async_show_form(step_id="user", data_schema=schema)
