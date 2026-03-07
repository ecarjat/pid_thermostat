"""Config flow for pid_thermostat."""

from __future__ import annotations

from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import CONF_NAME

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

try:
    from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig
except ImportError:  # pragma: no cover - compatibility fallback for older HA
    EntitySelector = None
    EntitySelectorConfig = None


def _entity_field():
    """Return entity selector when available, fallback to string."""
    if EntitySelector is None or EntitySelectorConfig is None:
        return str
    return EntitySelector(EntitySelectorConfig())


def _normalize_seconds(value):
    """Normalize imported time values to integer seconds."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    try:
        return int(cv.time_period(value).total_seconds())
    except (TypeError, ValueError, vol.Invalid):
        return value


def _normalize_import_data(user_input):
    """Normalize YAML-imported data into config-entry format."""
    data = dict(user_input)
    data.setdefault(CONF_NAME, DEFAULT_NAME)

    keep_alive = _normalize_seconds(data.get(CONF_KEEP_ALIVE))
    if keep_alive is not None:
        data[CONF_KEEP_ALIVE] = keep_alive

    min_cycle = _normalize_seconds(data.get(CONF_MIN_DUR))
    if min_cycle == 0:
        data.pop(CONF_MIN_DUR, None)
    elif min_cycle is not None:
        data[CONF_MIN_DUR] = min_cycle

    return data


def _normalize_options_data(user_input):
    """Normalize options form values into config-entry option format."""
    data = dict(user_input)

    keep_alive = _normalize_seconds(data.get(CONF_KEEP_ALIVE))
    if keep_alive is not None:
        data[CONF_KEEP_ALIVE] = keep_alive

    min_cycle = _normalize_seconds(data.get(CONF_MIN_DUR))
    if min_cycle == 0:
        data.pop(CONF_MIN_DUR, None)
    elif min_cycle is not None:
        data[CONF_MIN_DUR] = min_cycle

    return data


def _build_user_schema():
    """Schema for initial user setup."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_HEATER): _entity_field(),
            vol.Required(CONF_SENSOR): _entity_field(),
            vol.Required(CONF_KEEP_ALIVE, default=DEFAULT_KEEP_ALIVE_SECONDS): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
            vol.Optional(CONF_AC_MODE, default=False): bool,
            vol.Optional(CONF_MIN_DUR, default=0): vol.All(
                vol.Coerce(int), vol.Range(min=0)
            ),
            vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
            vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
            vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
            vol.Optional(CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(
                float
            ),
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
            vol.Optional(CONF_NOISEBAND, default=DEFAULT_NOISEBAND): vol.Coerce(float),
        }
    )


def _build_options_schema(defaults):
    """Schema for options editing after setup."""
    keep_alive_default = _normalize_seconds(defaults.get(CONF_KEEP_ALIVE))
    if keep_alive_default is None:
        keep_alive_default = DEFAULT_KEEP_ALIVE_SECONDS

    min_cycle_default = _normalize_seconds(defaults.get(CONF_MIN_DUR))
    if min_cycle_default is None:
        min_cycle_default = 0

    def _optional_float(field):
        default = defaults.get(field)
        if default is None:
            return vol.Optional(field)
        return vol.Optional(field, default=default)

    def _optional_in(field):
        default = defaults.get(field)
        if default is None:
            return vol.Optional(field)
        return vol.Optional(field, default=default)

    return vol.Schema(
        {
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(CONF_KEEP_ALIVE, default=keep_alive_default): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
            vol.Optional(CONF_AC_MODE, default=defaults.get(CONF_AC_MODE, False)): bool,
            vol.Optional(CONF_MIN_DUR, default=min_cycle_default): vol.All(
                vol.Coerce(int), vol.Range(min=0)
            ),
            _optional_float(CONF_MIN_TEMP): vol.Coerce(float),
            _optional_float(CONF_MAX_TEMP): vol.Coerce(float),
            _optional_float(CONF_TARGET_TEMP): vol.Coerce(float),
            vol.Optional(
                CONF_COLD_TOLERANCE,
                default=defaults.get(CONF_COLD_TOLERANCE, DEFAULT_TOLERANCE),
            ): vol.Coerce(float),
            vol.Optional(
                CONF_HOT_TOLERANCE,
                default=defaults.get(CONF_HOT_TOLERANCE, DEFAULT_TOLERANCE),
            ): vol.Coerce(float),
            _optional_in(CONF_INITIAL_HVAC_MODE): vol.In(
                [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]
            ),
            _optional_float(CONF_AWAY_TEMP): vol.Coerce(float),
            _optional_in(CONF_PRECISION): vol.In([0.1, 0.5, 1.0]),
            vol.Optional(
                CONF_DIFFERENCE,
                default=defaults.get(CONF_DIFFERENCE, DEFAULT_DIFFERENCE),
            ): vol.Coerce(float),
            vol.Optional(
                CONF_KP, default=defaults.get(CONF_KP, DEFAULT_KP)
            ): vol.Coerce(float),
            vol.Optional(
                CONF_KI, default=defaults.get(CONF_KI, DEFAULT_KI)
            ): vol.Coerce(float),
            vol.Optional(
                CONF_KD, default=defaults.get(CONF_KD, DEFAULT_KD)
            ): vol.Coerce(float),
            vol.Optional(
                CONF_PWM, default=defaults.get(CONF_PWM, DEFAULT_PWM)
            ): vol.Coerce(float),
            vol.Optional(
                CONF_AUTOTUNE,
                default=defaults.get(CONF_AUTOTUNE, DEFAULT_AUTOTUNE),
            ): vol.In(AUTOTUNE_RULES),
            vol.Optional(
                CONF_NOISEBAND,
                default=defaults.get(CONF_NOISEBAND, DEFAULT_NOISEBAND),
            ): vol.Coerce(float),
        }
    )


class PIDThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for pid_thermostat."""

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return PIDThermostatOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Handle initial configuration step."""
        if user_input is not None:
            unique_id = f"{user_input[CONF_HEATER]}::{user_input[CONF_SENSOR]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            if user_input.get(CONF_MIN_DUR) == 0:
                user_input.pop(CONF_MIN_DUR)
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=_build_user_schema(), errors={}
        )

    async def async_step_import(self, user_input=None):
        """Handle configuration import from YAML."""
        if user_input is None:
            return self.async_abort(reason="invalid_import")

        imported = _normalize_import_data(user_input)
        unique_id = f"{imported[CONF_HEATER]}::{imported[CONF_SENSOR]}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=imported[CONF_NAME], data=imported)


class PIDThermostatOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for pid_thermostat."""

    async def async_step_init(self, user_input=None):
        """Manage the integration options."""
        if user_input is not None:
            normalized = _normalize_options_data(user_input)
            return self.async_create_entry(title="", data=normalized)

        defaults = dict(self.config_entry.data)
        defaults.update(self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(defaults),
            errors={},
        )
