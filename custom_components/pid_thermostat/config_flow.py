"""Config flow for pid_thermostat."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import (
    AUTOTUNE_RULES,
    CONF_AC_MODE,
    CONF_AUTOTUNE,
    CONF_AWAY_TEMP,
    CONF_COLD_TOLERANCE,
    CONF_DIFFERENCE,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
    CONF_INITIAL_HVAC_MODE,
    CONF_KD,
    CONF_KEEP_ALIVE,
    CONF_KI,
    CONF_KP,
    CONF_MAX_TEMP,
    CONF_MIN_DUR,
    CONF_MIN_TEMP,
    CONF_NOISEBAND,
    CONF_PRECISION,
    CONF_PWM,
    CONF_SENSOR,
    CONF_TARGET_TEMP,
    DEFAULT_AUTOTUNE,
    DEFAULT_DIFFERENCE,
    DEFAULT_KD,
    DEFAULT_KEEP_ALIVE_SECONDS,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_NAME,
    DEFAULT_NOISEBAND,
    DEFAULT_PWM,
    DEFAULT_TOLERANCE,
    DOMAIN,
)


class PIDThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for pid_thermostat."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle initial configuration step."""
        if user_input is not None:
            unique_id = f"{user_input[CONF_HEATER]}::{user_input[CONF_SENSOR]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            if user_input.get(CONF_MIN_DUR) == 0:
                user_input.pop(CONF_MIN_DUR)
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_HEATER): EntitySelector(EntitySelectorConfig()),
                vol.Required(CONF_SENSOR): EntitySelector(EntitySelectorConfig()),
                vol.Required(
                    CONF_KEEP_ALIVE, default=DEFAULT_KEEP_ALIVE_SECONDS
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional(CONF_AC_MODE, default=False): bool,
                vol.Optional(CONF_MIN_DUR, default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0)
                ),
                vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
                vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
                vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
                vol.Optional(
                    CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE
                ): vol.Coerce(float),
                vol.Optional(CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(
                    float
                ),
                vol.Optional(CONF_INITIAL_HVAC_MODE): vol.In(
                    [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]
                ),
                vol.Optional(CONF_AWAY_TEMP): vol.Coerce(float),
                vol.Optional(CONF_PRECISION): vol.In([0.1, 0.5, 1.0]),
                vol.Optional(CONF_DIFFERENCE, default=DEFAULT_DIFFERENCE): vol.Coerce(
                    float
                ),
                vol.Optional(CONF_KP, default=DEFAULT_KP): vol.Coerce(float),
                vol.Optional(CONF_KI, default=DEFAULT_KI): vol.Coerce(float),
                vol.Optional(CONF_KD, default=DEFAULT_KD): vol.Coerce(float),
                vol.Optional(CONF_PWM, default=DEFAULT_PWM): vol.Coerce(float),
                vol.Optional(CONF_AUTOTUNE, default=DEFAULT_AUTOTUNE): vol.In(
                    AUTOTUNE_RULES
                ),
                vol.Optional(CONF_NOISEBAND, default=DEFAULT_NOISEBAND): vol.Coerce(
                    float
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors={})
