"""Adds support for smart (PID) thermostat units.
For more details about this platform, please refer to the documentation at
https://github.com/fabiannydegger/custom_components/"""

import asyncio
import logging
import time
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_PRESET_MODE,
    PRESET_AWAY,
    PRESET_HOME,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE  # , STATE_ON,
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
    EVENT_HOMEASSISTANT_START,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import DOMAIN as HA_DOMAIN
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

# from homeassistant.helpers import condition
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.pid_thermostat import pid_controller as pid_controller

_LOGGER = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 0.3
DEFAULT_NAME = "Smart Thermostat"
# To Do: set default for pt1
DEFAULT_DIFFERENCE = 100
DEFAULT_PWM = 0
DEFAULT_KP = 0
DEFAULT_KI = 0
DEFAULT_KD = 0
DEFAULT_AUTOTUNE = "none"
DEFAULT_NOISEBAND = 0.5
DEFAULT_KEEP_ALIVE_SECONDS = 60
AUTOTUNE_RULES = (
    DEFAULT_AUTOTUNE,
    "ziegler-nichols",
    "tyreus-luyben",
    "ciancone-marlin",
    "pessen-integral",
    "some-overshoot",
    "no-overshoot",
    "brewing",
)

CONF_HEATER = "heater"
CONF_SENSOR = "target_sensor"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_TARGET_TEMP = "target_temp"
CONF_AC_MODE = "ac_mode"
CONF_MIN_DUR = "min_cycle_duration"
CONF_COLD_TOLERANCE = "cold_tolerance"
CONF_HOT_TOLERANCE = "hot_tolerance"
CONF_KEEP_ALIVE = "keep_alive"
CONF_INITIAL_HVAC_MODE = "initial_hvac_mode"
CONF_AWAY_TEMP = "away_temp"
CONF_PRECISION = "precision"
CONF_DIFFERENCE = "difference"
CONF_KP = "kp"
CONF_KI = "ki"
CONF_KD = "kd"
CONF_PWM = "pwm"
CONF_AUTOTUNE = "autotune"
CONF_NOISEBAND = "noiseband"
ATTR_HOME_TEMP = "home_temp"
ATTR_AWAY_TEMP = "away_temp"
ATTR_PID_KP = "pid_kp"
ATTR_PID_KI = "pid_ki"
ATTR_PID_KD = "pid_kd"
ATTR_AUTOTUNE_MODE = "autotune_mode"

SUPPORT_FLAGS = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HEATER): cv.entity_id,
        vol.Required(CONF_SENSOR): cv.entity_id,
        vol.Optional(CONF_AC_MODE): cv.boolean,
        vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MIN_DUR): vol.All(cv.time_period, cv.positive_timedelta),
        vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
        vol.Optional(CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
        vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
        vol.Required(CONF_KEEP_ALIVE): vol.All(cv.time_period, cv.positive_timedelta),
        vol.Optional(CONF_INITIAL_HVAC_MODE): vol.In(
            [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]
        ),
        vol.Optional(CONF_AWAY_TEMP): vol.Coerce(float),
        vol.Optional(CONF_PRECISION): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]
        ),
        vol.Optional(CONF_DIFFERENCE, default=DEFAULT_DIFFERENCE): vol.Coerce(float),
        vol.Optional(CONF_KP, default=DEFAULT_KP): vol.Coerce(float),
        vol.Optional(CONF_KI, default=DEFAULT_KI): vol.Coerce(float),
        vol.Optional(CONF_KD, default=DEFAULT_KD): vol.Coerce(float),
        vol.Optional(CONF_PWM, default=DEFAULT_PWM): vol.Coerce(float),
        vol.Optional(CONF_AUTOTUNE, default=DEFAULT_AUTOTUNE): vol.In(AUTOTUNE_RULES),
        vol.Optional(CONF_NOISEBAND, default=DEFAULT_NOISEBAND): vol.Coerce(float),
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the generic thermostat platform."""
    async_add_entities([_build_thermostat(hass, config)])


async def async_setup_entry(
    hass, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up pid_thermostat from a config entry."""
    async_add_entities([_build_thermostat(hass, entry.data)])


def _as_timedelta(value, default_seconds=None):
    """Normalize a time config value into a timedelta."""
    if value is None:
        if default_seconds is None:
            return None
        return timedelta(seconds=default_seconds)
    if isinstance(value, timedelta):
        return value
    return timedelta(seconds=float(value))


def _build_thermostat(hass, config):
    """Build a SmartThermostat from YAML or config entry data."""
    name = config.get(CONF_NAME)
    heater_entity_id = config.get(CONF_HEATER)
    sensor_entity_id = config.get(CONF_SENSOR)
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)
    target_temp = config.get(CONF_TARGET_TEMP)
    ac_mode = config.get(CONF_AC_MODE)
    min_cycle_duration = _as_timedelta(config.get(CONF_MIN_DUR))
    cold_tolerance = config.get(CONF_COLD_TOLERANCE)
    hot_tolerance = config.get(CONF_HOT_TOLERANCE)
    keep_alive = _as_timedelta(
        config.get(CONF_KEEP_ALIVE),
        default_seconds=DEFAULT_KEEP_ALIVE_SECONDS,
    )
    initial_hvac_mode = config.get(CONF_INITIAL_HVAC_MODE)
    away_temp = config.get(CONF_AWAY_TEMP)
    precision = config.get(CONF_PRECISION)
    unit = hass.config.units.temperature_unit
    difference = config.get(CONF_DIFFERENCE, DEFAULT_DIFFERENCE)
    kp = config.get(CONF_KP, DEFAULT_KP)
    ki = config.get(CONF_KI, DEFAULT_KI)
    kd = config.get(CONF_KD, DEFAULT_KD)
    pwm = config.get(CONF_PWM, DEFAULT_PWM)
    autotune = config.get(CONF_AUTOTUNE, DEFAULT_AUTOTUNE)
    noiseband = config.get(CONF_NOISEBAND, DEFAULT_NOISEBAND)

    return SmartThermostat(
        name,
        heater_entity_id,
        sensor_entity_id,
        min_temp,
        max_temp,
        target_temp,
        ac_mode,
        min_cycle_duration,
        cold_tolerance,
        hot_tolerance,
        keep_alive,
        initial_hvac_mode,
        away_temp,
        precision,
        unit,
        difference,
        kp,
        ki,
        kd,
        pwm,
        autotune,
        noiseband,
    )


class SmartThermostat(ClimateEntity, RestoreEntity):
    """Representation of a Smart Thermostat device."""

    def __init__(
        self,
        name,
        heater_entity_id,
        sensor_entity_id,
        min_temp,
        max_temp,
        target_temp,
        ac_mode,
        min_cycle_duration,
        cold_tolerance,
        hot_tolerance,
        keep_alive,
        initial_hvac_mode,
        away_temp,
        precision,
        unit,
        difference,
        kp,
        ki,
        kd,
        pwm,
        autotune,
        noiseband,
    ):
        """Initialize the thermostat."""
        self._name = name
        self.heater_entity_id = heater_entity_id
        self.sensor_entity_id = sensor_entity_id
        self.ac_mode = ac_mode
        self.min_cycle_duration = min_cycle_duration
        self._cold_tolerance = cold_tolerance
        self._hot_tolerance = hot_tolerance
        self._keep_alive = keep_alive
        self._hvac_mode = initial_hvac_mode
        self._saved_target_temp = target_temp if target_temp is not None else away_temp
        self._temp_precision = precision
        if self.ac_mode:
            self._hvac_list = [HVACMode.COOL, HVACMode.OFF]
            self.minOut = -difference
            self.maxOut = 0
        else:
            self._hvac_list = [HVACMode.HEAT, HVACMode.OFF]
            self.minOut = 0
            self.maxOut = difference
        self._active = False
        self._cur_temp = None
        self._temp_lock = asyncio.Lock()
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._target_temp = target_temp
        self._unit = unit
        self._support_flags = SUPPORT_FLAGS
        if away_temp:
            self._support_flags = SUPPORT_FLAGS | ClimateEntityFeature.PRESET_MODE
        self._away_temp = away_temp
        self._is_away = False
        self.difference = difference
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.pwm = pwm
        self.autotune = autotune
        self.noiseband = noiseband
        self.sensor_entity_id = sensor_entity_id
        self.time_changed = time.time()
        self.control_output = 0
        self.pidController = None
        self.pidAutotune = None
        self._remove_callbacks = []

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Add listener
        self._remove_callbacks.append(
            async_track_state_change_event(
                self.hass, self.sensor_entity_id, self._async_sensor_changed
            )
        )
        self._remove_callbacks.append(
            async_track_state_change_event(
                self.hass, self.heater_entity_id, self._async_switch_changed
            )
        )

        if self._keep_alive:
            self._remove_callbacks.append(
                async_track_time_interval(
                    self.hass, self._async_control_heating, self._keep_alive
                )
            )

        @callback
        def _async_startup(event):
            """Init on startup."""
            sensor_state = self.hass.states.get(self.sensor_entity_id)
            if sensor_state and sensor_state.state != STATE_UNKNOWN:
                self._async_update_temp(sensor_state)

        self._remove_callbacks.append(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)
        )

        self._restore_previous_state(await self.async_get_last_state())

        # Set default state to off
        if not self._hvac_mode:
            self._hvac_mode = HVACMode.OFF

        self._initialize_controller()

    async def async_will_remove_from_hass(self):
        """Handle entity removal and cancel tracked listeners."""
        while self._remove_callbacks:
            remove_callback = self._remove_callbacks.pop()
            remove_callback()
        await super().async_will_remove_from_hass()

    def _restore_previous_state(self, old_state):
        """Restore thermostat values from previous Home Assistant state."""
        if old_state is None:
            if self._target_temp is None:
                if self.ac_mode:
                    self._target_temp = self.max_temp
                else:
                    self._target_temp = self.min_temp
            if self._saved_target_temp is None:
                self._saved_target_temp = self._target_temp
            _LOGGER.warning(
                "No previously saved temperature, setting to %s", self._target_temp
            )
            return

        if old_state.attributes.get(ATTR_HOME_TEMP) is not None:
            self._saved_target_temp = float(old_state.attributes[ATTR_HOME_TEMP])
        if old_state.attributes.get(ATTR_AWAY_TEMP) is not None:
            self._away_temp = float(old_state.attributes[ATTR_AWAY_TEMP])
        if old_state.attributes.get(ATTR_PID_KP) is not None:
            self.kp = float(old_state.attributes[ATTR_PID_KP])
        if old_state.attributes.get(ATTR_PID_KI) is not None:
            self.ki = float(old_state.attributes[ATTR_PID_KI])
        if old_state.attributes.get(ATTR_PID_KD) is not None:
            self.kd = float(old_state.attributes[ATTR_PID_KD])
        restored_autotune = old_state.attributes.get(ATTR_AUTOTUNE_MODE)
        if restored_autotune in AUTOTUNE_RULES:
            self.autotune = restored_autotune
        elif restored_autotune is not None:
            self.autotune = DEFAULT_AUTOTUNE

        if self._target_temp is None:
            restored_target = old_state.attributes.get(ATTR_TEMPERATURE)
            if restored_target is None:
                if self.ac_mode:
                    self._target_temp = self.max_temp
                else:
                    self._target_temp = self.min_temp
                _LOGGER.warning(
                    "Undefined target temperature, falling back to %s",
                    self._target_temp,
                )
            else:
                self._target_temp = float(restored_target)

        if old_state.attributes.get(ATTR_PRESET_MODE) == PRESET_AWAY:
            self._is_away = True
        if not self._hvac_mode and old_state.state:
            self._hvac_mode = old_state.state

        if self._is_away and self._saved_target_temp is None:
            self._saved_target_temp = self._target_temp
        elif not self._is_away and self._target_temp is not None:
            self._saved_target_temp = self._target_temp

    def _initialize_controller(self):
        """Build the active control object based on current configuration."""
        self.pidController = None
        self.pidAutotune = None
        if self.autotune != DEFAULT_AUTOTUNE:
            self._initialize_autotune_controller()
            return
        self._initialize_pid_controller()

    def _initialize_pid_controller(self):
        """Build a PID controller using current PID parameters."""
        self.pidController = pid_controller.PIDArduino(
            self._keep_alive.total_seconds(),
            self.kp,
            self.ki,
            self.kd,
            self.minOut,
            self.maxOut,
            time.time,
        )

    def _initialize_autotune_controller(self):
        """Build an autotune controller when a target temperature is available."""
        if self._target_temp is None:
            _LOGGER.warning(
                "Autotune requested but target temperature is unknown. "
                "Autotune will start after a target is set."
            )
            return
        self.pidAutotune = pid_controller.PIDAutotune(
            self._target_temp,
            self.difference,
            self._keep_alive.total_seconds(),
            self._keep_alive.total_seconds(),
            self.minOut,
            self.maxOut,
            self.noiseband,
            time.time,
        )
        _LOGGER.warning(
            "Autotune will run with the next setpoint value. "
            "Changes submitted after start have no effect until it finishes."
        )

    def _ensure_controller_initialized(self):
        """Ensure the active control object exists before use."""
        if self.autotune != DEFAULT_AUTOTUNE:
            if self.pidAutotune is None:
                self._initialize_autotune_controller()
            return
        if self.pidController is None:
            self._initialize_pid_controller()

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def precision(self):
        """Return the precision of the system."""
        if self._temp_precision is not None:
            return self._temp_precision
        return super().precision

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def current_temperature(self):
        """Return the sensor temperature."""
        return self._cur_temp

    @property
    def hvac_mode(self):
        """Return current operation."""
        return self._hvac_mode

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.
        Need to be one of HVACAction
        """
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if not self._is_device_active:
            return HVACAction.IDLE
        if self.ac_mode:
            return HVACAction.COOLING
        return HVACAction.HEATING

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_list

    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., home, away, temp."""
        if self._is_away:
            return PRESET_AWAY
        return PRESET_HOME

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        if self._away_temp is not None:
            return [PRESET_AWAY, PRESET_HOME]
        return None

    @property
    def extra_state_attributes(self):
        """Return state attributes persisted by RestoreEntity."""
        attrs = {}
        if self._saved_target_temp is not None:
            attrs[ATTR_HOME_TEMP] = self._saved_target_temp
        if self._away_temp is not None:
            attrs[ATTR_AWAY_TEMP] = self._away_temp
        attrs[ATTR_PID_KP] = self.kp
        attrs[ATTR_PID_KI] = self.ki
        attrs[ATTR_PID_KD] = self.kd
        attrs[ATTR_AUTOTUNE_MODE] = self.autotune
        return attrs

    @property
    def pid_parm(self):
        """Return the pid parameters of the thermostat."""
        return (self.kp, self.ki, self.kd)

    @property
    def pid_control_output(self):
        """Return the pid control output of the thermostat."""
        return self.control_output

    async def async_set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode == HVACMode.HEAT:
            self._hvac_mode = HVACMode.HEAT
            await self._async_control_heating(force=True)
        elif hvac_mode == HVACMode.COOL:
            self._hvac_mode = HVACMode.COOL
            await self._async_control_heating(force=True)
        elif hvac_mode == HVACMode.OFF:
            self._hvac_mode = HVACMode.OFF
            if self._is_device_active:
                await self._async_heater_turn_off(force=True)
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return
        # Ensure we update the current operation after changing the mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._target_temp = temperature
        if self._is_away and self._away_temp is not None:
            self._away_temp = temperature
        elif not self._is_away:
            self._saved_target_temp = temperature
        if self.autotune != DEFAULT_AUTOTUNE:
            self._initialize_autotune_controller()
        self._ensure_controller_initialized()
        await self._async_control_heating(force=True)
        self.async_write_ha_state()

    async def async_set_pid(self, kp, ki, kd):
        """Set PID parameters."""
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.autotune = DEFAULT_AUTOTUNE
        self.pidAutotune = None
        self._initialize_pid_controller()
        await self._async_control_heating(force=True)
        self.async_write_ha_state()

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self._min_temp:
            return self._min_temp

        # get default temp from super class
        return super().min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self._max_temp:
            return self._max_temp

        # Get default temp from super class
        return super().max_temp

    async def _async_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle temperature changes."""
        new_state = event.data["new_state"]
        if new_state is None:
            return

        self._async_update_temp(new_state)
        # await self._async_control_heating()
        self.async_write_ha_state()

    @callback
    def _async_switch_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle heater switch state changes."""
        new_state = event.data["new_state"]
        if new_state is None:
            return
        self.async_schedule_update_ha_state()

    @callback
    def _async_update_temp(self, state):
        """Update thermostat with latest state from sensor."""
        try:
            if state.state is not None and state.state != "unknown":
                self._cur_temp = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s", ex)

    async def _async_control_heating(self, time=None, force=False):
        """Run PID controller, optional autotune for faster integration"""
        async with self._temp_lock:
            self._ensure_controller_initialized()
            if not self._active and None not in (self._cur_temp, self._target_temp):
                self._active = True
                _LOGGER.info(
                    "Obtained current and target temperature. "
                    "Smart thermostat active. %s, %s",
                    self._cur_temp,
                    self._target_temp,
                )

            if not self._active or self._hvac_mode == HVACMode.OFF:
                return

            # if not force and time is None:
            #    # If the `force` argument is True, we
            #    # ignore `min_cycle_duration`.
            #    # If the `time` argument is not none, we were invoked for
            #    # keep-alive purposes, and `min_cycle_duration` is irrelevant.
            #    if self.min_cycle_duration:
            #        if self._is_device_active:
            #            current_state = STATE_ON
            #        else:
            #            current_state = STATE_OFF
            #        long_enough = condition.state(
            #            self.hass, self.heater_entity_id, current_state,
            #            self.min_cycle_duration)
            #        if not long_enough:
            #            return

            # self.calc_output()
            await self.calc_output(force=force)

    @property
    def _is_device_active(self):
        """Return True when the controlled entity is active."""
        active = self.hass.states.get(self.heater_entity_id)
        if active is None:
            return False
        state = active.state
        _LOGGER.debug("_isactive: %s", state)
        return self._state_to_active(state)

    @staticmethod
    def _state_to_active(state):
        """Normalize heater states from different entity types."""
        if state is None:
            return False
        state_text = str(state).strip().lower()
        if state_text in {"off", "idle", "unknown", "unavailable"}:
            return False
        if state_text in {"on", "heating", "cooling"}:
            return True
        try:
            return float(state_text) != 0.0
        except ValueError:
            return True

    def _can_toggle(self, force):
        """Return True when min_cycle_duration allows a state transition."""
        if force or self.min_cycle_duration is None:
            return True
        elapsed = time.time() - self.time_changed
        min_cycle_seconds = self.min_cycle_duration.total_seconds()
        if elapsed >= min_cycle_seconds:
            return True
        _LOGGER.debug(
            "Skipping state transition for %s, min_cycle_duration active "
            "(%.2fs remaining)",
            self.heater_entity_id,
            min_cycle_seconds - elapsed,
        )
        return False

        # return self.hass.states.is_state(self.heater_entity_id, STATE_ON)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    async def _async_heater_turn_on(self, force=False):
        """Turn heater toggleable device on."""
        if self._is_device_active:
            return
        if not self._can_toggle(force):
            return
        data = {ATTR_ENTITY_ID: self.heater_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)
        self.time_changed = time.time()

    async def _async_heater_turn_off(self, force=False):
        """Turn heater toggleable device off."""
        if not self._is_device_active:
            return
        if not self._can_toggle(force):
            return
        data = {ATTR_ENTITY_ID: self.heater_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)
        self.time_changed = time.time()

    async def async_set_preset_mode(self, preset_mode: str):
        """Set new preset mode.
        This method must be run in the event loop and returns a coroutine.
        """
        if preset_mode == PRESET_AWAY and not self._is_away:
            self._is_away = True
            self._saved_target_temp = self._target_temp
            self._target_temp = self._away_temp
            if self.autotune != DEFAULT_AUTOTUNE:
                self._initialize_autotune_controller()
            self._ensure_controller_initialized()
            await self._async_control_heating(force=True)
        elif preset_mode == PRESET_HOME and self._is_away:
            self._is_away = False
            self._target_temp = self._saved_target_temp
            if self.autotune != DEFAULT_AUTOTUNE:
                self._initialize_autotune_controller()
            self._ensure_controller_initialized()
            await self._async_control_heating(force=True)

        self.async_write_ha_state()

    async def calc_output(self, force=False):
        """calculate control output and handle autotune"""
        _LOGGER.info(
            "Start calc_output - Current temp: %s, Target temp: %s",
            self._cur_temp,
            self._target_temp,
        )
        if self.autotune != DEFAULT_AUTOTUNE:
            _LOGGER.info("in autotune")
            if self.pidAutotune is None:
                return
            if self.pidAutotune.run(self._cur_temp):
                params = self.pidAutotune.get_pid_parameters(self.autotune)
                self.kp = params.Kp
                self.ki = params.Ki
                self.kd = params.Kd
                _LOGGER.warning(
                    "Set Kd, Ki, Kd. "
                    "Smart thermostat now runs on PID Controller. %s,  %s,  %s",
                    self.kp,
                    self.ki,
                    self.kd,
                )
                self.autotune = DEFAULT_AUTOTUNE
                self._initialize_pid_controller()
            self.control_output = self.pidAutotune.output
        else:
            if self.pidController is None:
                self._initialize_pid_controller()
            self.control_output = self.pidController.calc(
                self._cur_temp, self._target_temp
            )
            _LOGGER.info(
                "Current temp: %s, Target temp: %s", self._cur_temp, self._target_temp
            )
        _LOGGER.info("Obtained current control output. %s", self.control_output)
        await self.set_controlvalue(force=force)

    async def set_controlvalue(self, force=False):
        """Set Outputvalue for heater"""
        if self.pwm:
            if (
                self.control_output == self.difference
                or self.control_output == -self.difference
            ):
                if not self._is_device_active:
                    _LOGGER.info("Turning on AC %s", self.heater_entity_id)
                    await self._async_heater_turn_on(force=force)
            elif self.control_output > 0:
                if self.maxOut == 0:
                    return
                ratio = max(0.0, min(1.0, self.control_output / self.maxOut))
                await self.pwm_switch(
                    self.pwm * ratio,
                    self.pwm * (1.0 - ratio),
                    time.time() - self.time_changed,
                    force=force,
                )
            elif self.control_output < 0:
                if self.minOut == 0:
                    return
                ratio = max(0.0, min(1.0, self.control_output / self.minOut))
                off_ratio = max(
                    0.0,
                    min(1.0, (self.minOut - self.control_output) / self.minOut),
                )
                await self.pwm_switch(
                    self.pwm * ratio,
                    self.pwm * off_ratio,
                    time.time() - self.time_changed,
                    force=force,
                )
            else:
                if self._active:
                    _LOGGER.info("Turning off heater %s", self.heater_entity_id)
                    await self._async_heater_turn_off(force=force)
        else:
            _LOGGER.info(
                "Change state of heater %s to %s",
                self.heater_entity_id,
                self.control_output,
            )
            self.hass.states.async_set(self.heater_entity_id, self.control_output)

    async def pwm_switch(self, time_on, time_off, time_passed, force=False):
        """turn off and on the heater proportionally to controlvalue."""
        if self._is_device_active:
            if time_on < time_passed:
                _LOGGER.info("Turning off AC %s", self.heater_entity_id)
                await self._async_heater_turn_off(force=force)
            else:
                _LOGGER.info(
                    "Time until %s turns off: %s sec",
                    self.heater_entity_id,
                    time_on - time_passed,
                )
        else:
            if time_off < time_passed:
                _LOGGER.info("Turning on AC %s", self.heater_entity_id)
                await self._async_heater_turn_on(force=force)
            else:
                _LOGGER.info(
                    "Time until %s turns on: %s sec",
                    self.heater_entity_id,
                    time_off - time_passed,
                )
