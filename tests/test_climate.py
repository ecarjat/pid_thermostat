from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON

from custom_components.pid_thermostat import climate


class DummyState:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class DummyStates:
    def __init__(self):
        self._states = {}

    def get(self, entity_id):
        return self._states.get(entity_id)

    def set(self, entity_id, state):
        self._states[entity_id] = DummyState(state)

    def async_set(self, entity_id, state):
        self.set(entity_id, state)


class DummyServices:
    def __init__(self, states):
        self.calls = []
        self._states = states

    async def async_call(self, domain, service, data):
        self.calls.append((domain, service, data))
        entity_id = data["entity_id"]
        if service == SERVICE_TURN_ON:
            self._states.set(entity_id, "on")
        elif service == SERVICE_TURN_OFF:
            self._states.set(entity_id, "off")


class DummyHass:
    def __init__(self):
        self.states = DummyStates()
        self.services = DummyServices(self.states)


def build_thermostat(
    *,
    target_temp=21.0,
    ac_mode=False,
    min_cycle_duration=timedelta(seconds=0),
    autotune=climate.DEFAULT_AUTOTUNE,
    pwm=0,
    away_temp=None,
):
    thermostat = climate.SmartThermostat(
        "test",
        "switch.heater",
        "sensor.temp",
        10.0,
        35.0,
        target_temp,
        ac_mode,
        min_cycle_duration,
        0.3,
        0.3,
        timedelta(seconds=10),
        climate.HVACMode.HEAT if not ac_mode else climate.HVACMode.COOL,
        away_temp,
        None,
        "C",
        100.0,
        1.0,
        0.1,
        0.01,
        pwm,
        autotune,
        0.5,
    )
    thermostat.hass = DummyHass()
    thermostat.hass.states.set(thermostat.heater_entity_id, "off")
    thermostat.async_write_ha_state = Mock()
    return thermostat


def test_schema_rejects_invalid_autotune_value():
    config = {
        climate.CONF_HEATER: "switch.heater",
        climate.CONF_SENSOR: "sensor.temp",
        climate.CONF_KEEP_ALIVE: timedelta(seconds=10),
        climate.CONF_AUTOTUNE: "invalid-rule",
    }
    with pytest.raises(vol.Invalid):
        climate.PLATFORM_SCHEMA(config)


def test_autotune_init_waits_for_target_temp():
    thermostat = build_thermostat(
        target_temp=None,
        autotune="ziegler-nichols",
    )
    thermostat._initialize_controller()
    assert thermostat.pidAutotune is None

    thermostat._target_temp = 22.0
    thermostat._ensure_controller_initialized()
    assert thermostat.pidAutotune is not None


@pytest.mark.asyncio
async def test_cooling_pwm_negative_output_calls_pwm_without_crashing():
    thermostat = build_thermostat(ac_mode=True, pwm=10)
    thermostat.control_output = -40
    thermostat._active = True
    thermostat.pwm_switch = AsyncMock()

    await thermostat.set_controlvalue()

    thermostat.pwm_switch.assert_awaited_once()
    args, kwargs = thermostat.pwm_switch.await_args
    assert args[0] == pytest.approx(4.0)
    assert args[1] == pytest.approx(6.0)
    assert kwargs["force"] is False


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("off", False),
        ("idle", False),
        ("unknown", False),
        ("unavailable", False),
        ("0", False),
        ("0.0", False),
        ("on", True),
        ("heating", True),
        ("cooling", True),
        ("1", True),
        ("-1", True),
        ("custom-active", True),
    ],
)
def test_state_to_active_normalization(state, expected):
    assert climate.SmartThermostat._state_to_active(state) is expected


def test_is_device_active_handles_switch_off_state():
    thermostat = build_thermostat()
    thermostat.hass.states.set(thermostat.heater_entity_id, "off")
    assert thermostat._is_device_active is False

    thermostat.hass.states.set(thermostat.heater_entity_id, "on")
    assert thermostat._is_device_active is True


@pytest.mark.asyncio
async def test_async_set_pid_disables_autotune_rebuilds_controller_and_forces_recalc():
    thermostat = build_thermostat(target_temp=21.0, autotune="ziegler-nichols")
    thermostat._initialize_controller()
    thermostat._async_control_heating = AsyncMock()

    await thermostat.async_set_pid(5.0, 1.0, 0.2)

    assert thermostat.autotune == climate.DEFAULT_AUTOTUNE
    assert thermostat.pidAutotune is None
    assert thermostat.pidController is not None
    assert thermostat.pidController._Kp == pytest.approx(5.0)
    thermostat._async_control_heating.assert_awaited_once_with(force=True)
    thermostat.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_min_cycle_duration_blocks_and_allows_switching(monkeypatch):
    thermostat = build_thermostat(min_cycle_duration=timedelta(seconds=120))
    now = 1000.0
    thermostat.time_changed = now

    monkeypatch.setattr(climate.time, "time", lambda: now + 10)
    await thermostat._async_heater_turn_on(force=False)
    assert thermostat.hass.services.calls == []

    await thermostat._async_heater_turn_on(force=True)
    assert len(thermostat.hass.services.calls) == 1

    monkeypatch.setattr(climate.time, "time", lambda: now + 20)
    await thermostat._async_heater_turn_off(force=False)
    assert len(thermostat.hass.services.calls) == 1

    monkeypatch.setattr(climate.time, "time", lambda: now + 200)
    await thermostat._async_heater_turn_off(force=False)
    assert len(thermostat.hass.services.calls) == 2


def test_restore_previous_state_persists_home_and_away_when_away():
    thermostat = build_thermostat(target_temp=None, away_temp=17.0)
    thermostat._saved_target_temp = None
    thermostat._target_temp = None
    thermostat._is_away = False

    old_state = DummyState(
        climate.HVACMode.HEAT,
        {
            climate.ATTR_TEMPERATURE: 16.0,
            climate.ATTR_PRESET_MODE: climate.PRESET_AWAY,
            climate.ATTR_HOME_TEMP: 22.0,
            climate.ATTR_AWAY_TEMP: 16.0,
        },
    )

    thermostat._restore_previous_state(old_state)

    assert thermostat._is_away is True
    assert thermostat._target_temp == pytest.approx(16.0)
    assert thermostat._saved_target_temp == pytest.approx(22.0)
    assert thermostat._away_temp == pytest.approx(16.0)


def test_restore_previous_state_persists_home_and_away_when_home():
    thermostat = build_thermostat(target_temp=None, away_temp=16.0)
    thermostat._saved_target_temp = None
    thermostat._target_temp = None
    thermostat._is_away = False

    old_state = DummyState(
        climate.HVACMode.HEAT,
        {
            climate.ATTR_TEMPERATURE: 21.5,
            climate.ATTR_PRESET_MODE: climate.PRESET_HOME,
            climate.ATTR_HOME_TEMP: 21.5,
            climate.ATTR_AWAY_TEMP: 16.0,
        },
    )

    thermostat._restore_previous_state(old_state)

    assert thermostat._is_away is False
    assert thermostat._target_temp == pytest.approx(21.5)
    assert thermostat._saved_target_temp == pytest.approx(21.5)
    assert thermostat._away_temp == pytest.approx(16.0)


def test_restore_previous_state_restores_pid_runtime_values():
    thermostat = build_thermostat(target_temp=21.0, away_temp=16.0)
    thermostat.kp = 1.0
    thermostat.ki = 0.1
    thermostat.kd = 0.01
    thermostat.autotune = climate.DEFAULT_AUTOTUNE

    old_state = DummyState(
        climate.HVACMode.HEAT,
        {
            climate.ATTR_PID_KP: 8.0,
            climate.ATTR_PID_KI: 0.5,
            climate.ATTR_PID_KD: 0.2,
            climate.ATTR_AUTOTUNE_MODE: "ziegler-nichols",
        },
    )

    thermostat._restore_previous_state(old_state)

    assert thermostat.kp == pytest.approx(8.0)
    assert thermostat.ki == pytest.approx(0.5)
    assert thermostat.kd == pytest.approx(0.2)
    assert thermostat.autotune == "ziegler-nichols"


@pytest.mark.asyncio
async def test_async_set_temperature_updates_preset_specific_value():
    thermostat = build_thermostat(target_temp=21.0, away_temp=16.0)
    thermostat._async_control_heating = AsyncMock()

    thermostat._is_away = False
    await thermostat.async_set_temperature(**{climate.ATTR_TEMPERATURE: 22.0})
    assert thermostat._saved_target_temp == pytest.approx(22.0)
    assert thermostat._away_temp == pytest.approx(16.0)

    thermostat._is_away = True
    await thermostat.async_set_temperature(**{climate.ATTR_TEMPERATURE: 15.5})
    assert thermostat._away_temp == pytest.approx(15.5)
    assert thermostat._saved_target_temp == pytest.approx(22.0)


def test_extra_state_attributes_expose_home_and_away_setpoints():
    thermostat = build_thermostat(target_temp=21.0, away_temp=16.0)
    thermostat._saved_target_temp = 22.5

    attrs = thermostat.extra_state_attributes
    assert attrs[climate.ATTR_HOME_TEMP] == pytest.approx(22.5)
    assert attrs[climate.ATTR_AWAY_TEMP] == pytest.approx(16.0)
    assert attrs[climate.ATTR_PID_KP] == pytest.approx(1.0)
    assert attrs[climate.ATTR_PID_KI] == pytest.approx(0.1)
    assert attrs[climate.ATTR_PID_KD] == pytest.approx(0.01)
    assert attrs[climate.ATTR_AUTOTUNE_MODE] == climate.DEFAULT_AUTOTUNE
