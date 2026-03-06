"""Integration-style restore lifecycle tests for pid_thermostat."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate.const import ATTR_PRESET_MODE, PRESET_AWAY
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pid_thermostat import climate

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

DOMAIN = "pid_thermostat"


def _entry_data():
    return {
        climate.CONF_NAME: "Office Thermostat",
        climate.CONF_HEATER: "switch.office_heater",
        climate.CONF_SENSOR: "sensor.office_temperature",
        climate.CONF_KEEP_ALIVE: 30,
        climate.CONF_KP: 1.0,
        climate.CONF_KI: 0.1,
        climate.CONF_KD: 0.01,
        climate.CONF_AUTOTUNE: climate.DEFAULT_AUTOTUNE,
        climate.CONF_AWAY_TEMP: 16.0,
    }


@pytest.mark.asyncio
async def test_restore_state_restores_home_away_and_pid_runtime(hass):
    """Config entry startup restores persisted setpoints and PID runtime values."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Office Thermostat", data=_entry_data()
    )
    entry.add_to_hass(hass)

    restored = State(
        "climate.office_thermostat",
        "heat",
        {
            ATTR_TEMPERATURE: 16.0,
            ATTR_PRESET_MODE: PRESET_AWAY,
            climate.ATTR_HOME_TEMP: 22.0,
            climate.ATTR_AWAY_TEMP: 16.0,
            climate.ATTR_PID_KP: 7.0,
            climate.ATTR_PID_KI: 0.4,
            climate.ATTR_PID_KD: 0.2,
            climate.ATTR_AUTOTUNE_MODE: "ziegler-nichols",
        },
    )

    with patch.object(
        climate.SmartThermostat,
        "async_get_last_state",
        AsyncMock(return_value=restored),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    states = hass.states.async_all("climate")
    assert len(states) == 1
    entity = states[0]
    assert entity.attributes[ATTR_TEMPERATURE] == pytest.approx(16.0)
    assert entity.attributes[climate.ATTR_HOME_TEMP] == pytest.approx(22.0)
    assert entity.attributes[climate.ATTR_AWAY_TEMP] == pytest.approx(16.0)
    assert entity.attributes[climate.ATTR_PID_KP] == pytest.approx(7.0)
    assert entity.attributes[climate.ATTR_PID_KI] == pytest.approx(0.4)
    assert entity.attributes[climate.ATTR_PID_KD] == pytest.approx(0.2)
    assert entity.attributes[climate.ATTR_AUTOTUNE_MODE] == "ziegler-nichols"
    assert entity.attributes[ATTR_PRESET_MODE] == PRESET_AWAY

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_restored_home_temp_is_used_when_leaving_away(hass):
    """When restoring in away mode, returning home uses restored home setpoint."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Office Thermostat", data=_entry_data()
    )
    entry.add_to_hass(hass)

    restored = State(
        "climate.office_thermostat",
        "heat",
        {
            ATTR_TEMPERATURE: 16.0,
            ATTR_PRESET_MODE: PRESET_AWAY,
            climate.ATTR_HOME_TEMP: 22.5,
            climate.ATTR_AWAY_TEMP: 16.0,
        },
    )

    with patch.object(
        climate.SmartThermostat,
        "async_get_last_state",
        AsyncMock(return_value=restored),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = hass.states.async_all("climate")[0].entity_id
    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": entity_id, "preset_mode": "home"},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[ATTR_PRESET_MODE] == "home"
    assert state.attributes[ATTR_TEMPERATURE] == pytest.approx(22.5)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
