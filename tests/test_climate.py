from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON

from custom_components.pid_thermostat import climate


class DummyState:
    def __init__(self, state, attributes=None, last_changed=None):
        self.state = state
        self.attributes = attributes or {}
        self.last_changed = last_changed


class DummyStates:
    def __init__(self):
        self._states = {}

    def get(self, entity_id):
        return self._states.get(entity_id)

    def set(self, entity_id, state, last_changed=None):
        self._states[entity_id] = DummyState(state, last_changed=last_changed)

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
        self.config = SimpleNamespace(units=SimpleNamespace(temperature_unit="C"))
        self.config_entries = SimpleNamespace(
            flow=SimpleNamespace(async_init=AsyncMock())
        )


def build_thermostat(
    *,
    target_temp=21.0,
    ac_mode=False,
    min_temp=10.0,
    max_temp=35.0,
    min_cycle_duration=timedelta(seconds=0),
    autotune=climate.DEFAULT_AUTOTUNE,
    pwm=0,
    away_temp=None,
):
    thermostat = climate.SmartThermostat(
        "test",
        "switch.heater",
        "sensor.temp",
        min_temp,
        max_temp,
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
    thermostat.async_schedule_update_ha_state = Mock()
    return thermostat


@pytest.mark.asyncio
async def test_async_setup_platform_imports_yaml_to_config_entry():
    hass = DummyHass()
    added = []
    config = {
        "platform": "pid_thermostat",
        climate.CONF_NAME: "Office",
        climate.CONF_HEATER: "switch.heater",
        climate.CONF_SENSOR: "sensor.temp",
        climate.CONF_KEEP_ALIVE: timedelta(seconds=45),
    }

    await climate.async_setup_platform(hass, config, lambda entities: added.extend(entities))

    hass.config_entries.flow.async_init.assert_awaited_once()
    _, kwargs = hass.config_entries.flow.async_init.await_args
    assert kwargs["context"]["source"] == "import"
    assert kwargs["data"][climate.CONF_HEATER] == "switch.heater"
    assert "platform" not in kwargs["data"]
    assert added == []


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
async def test_async_set_hvac_mode_rejects_unsupported_mode():
    thermostat = build_thermostat(ac_mode=False)
    thermostat._hvac_mode = climate.HVACMode.HEAT
    thermostat._async_control_heating = AsyncMock()

    await thermostat.async_set_hvac_mode(climate.HVACMode.COOL)

    assert thermostat._hvac_mode == climate.HVACMode.HEAT
    thermostat._async_control_heating.assert_not_called()
    thermostat.async_write_ha_state.assert_not_called()


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


def test_min_cycle_baseline_uses_state_timestamp(monkeypatch):
    thermostat = build_thermostat(min_cycle_duration=timedelta(seconds=120))
    baseline = 1000.0
    thermostat._sync_time_changed_from_state(
        DummyState(
            "off",
            last_changed=datetime.fromtimestamp(baseline, tz=timezone.utc),
        )
    )

    monkeypatch.setattr(climate.time, "time", lambda: baseline + 60)
    assert thermostat._can_toggle(force=False) is False

    monkeypatch.setattr(climate.time, "time", lambda: baseline + 130)
    assert thermostat._can_toggle(force=False) is True


@pytest.mark.asyncio
async def test_external_switch_toggle_updates_cycle_baseline(monkeypatch):
    thermostat = build_thermostat(min_cycle_duration=timedelta(seconds=120))
    transition_ts = 2000.0
    old_state = DummyState(
        "off",
        last_changed=datetime.fromtimestamp(transition_ts - 5, tz=timezone.utc),
    )
    new_state = DummyState(
        "on",
        last_changed=datetime.fromtimestamp(transition_ts, tz=timezone.utc),
    )
    thermostat.hass.states._states[thermostat.heater_entity_id] = new_state
    thermostat._async_switch_changed(
        SimpleNamespace(data={"old_state": old_state, "new_state": new_state})
    )

    assert thermostat.time_changed == pytest.approx(transition_ts)

    monkeypatch.setattr(climate.time, "time", lambda: transition_ts + 30)
    await thermostat._async_heater_turn_off(force=False)
    assert thermostat.hass.services.calls == []

    monkeypatch.setattr(climate.time, "time", lambda: transition_ts + 130)
    await thermostat._async_heater_turn_off(force=False)
    assert len(thermostat.hass.services.calls) == 1


def test_switch_changed_with_missing_old_state_updates_baseline():
    thermostat = build_thermostat(min_cycle_duration=timedelta(seconds=120))
    transition_ts = 2500.0
    thermostat.time_changed = 0.0
    new_state = DummyState(
        "on",
        last_changed=datetime.fromtimestamp(transition_ts, tz=timezone.utc),
    )
    thermostat._async_switch_changed(
        SimpleNamespace(data={"old_state": None, "new_state": new_state})
    )

    assert thermostat.time_changed == pytest.approx(transition_ts)
    thermostat.async_schedule_update_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_min_cycle_force_bypasses_for_on_and_off(monkeypatch):
    thermostat = build_thermostat(min_cycle_duration=timedelta(seconds=120))
    now = 3000.0
    thermostat.time_changed = now

    monkeypatch.setattr(climate.time, "time", lambda: now + 10)
    await thermostat._async_heater_turn_on(force=True)
    await thermostat._async_heater_turn_off(force=True)

    assert [call[1] for call in thermostat.hass.services.calls] == [
        SERVICE_TURN_ON,
        SERVICE_TURN_OFF,
    ]


def test_zero_values_are_not_treated_as_missing():
    thermostat = build_thermostat(min_temp=0.0, max_temp=0.0, away_temp=0.0)

    assert thermostat.min_temp == pytest.approx(0.0)
    assert thermostat.max_temp == pytest.approx(0.0)
    assert thermostat.preset_modes == [climate.PRESET_AWAY, climate.PRESET_HOME]


@pytest.mark.asyncio
async def test_sensor_update_triggers_control_recalculation():
    thermostat = build_thermostat()
    thermostat._async_control_heating = AsyncMock()
    event = SimpleNamespace(data={"new_state": DummyState("22.5")})

    await thermostat._async_sensor_changed(event)

    assert thermostat.current_temperature == pytest.approx(22.5)
    thermostat._async_control_heating.assert_awaited_once_with(force=False)
    thermostat.async_write_ha_state.assert_called_once()


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
