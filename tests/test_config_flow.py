"""Tests for pid_thermostat config flow and migrations."""

from __future__ import annotations

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.pid_thermostat as integration
from custom_components.pid_thermostat import climate

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

DOMAIN = "pid_thermostat"


@pytest.mark.asyncio
async def test_user_config_flow_creates_entry(hass):
    """Config flow should create an entry with expected normalized values."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            climate.CONF_NAME: "Office",
            climate.CONF_HEATER: "switch.heater_office",
            climate.CONF_SENSOR: "sensor.office_temp",
            climate.CONF_KEEP_ALIVE: 45,
            climate.CONF_MIN_DUR: 0,
            climate.CONF_AUTOTUNE: climate.DEFAULT_AUTOTUNE,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Office"
    assert result["data"][climate.CONF_KEEP_ALIVE] == 45
    assert climate.CONF_MIN_DUR not in result["data"]

    entry = result["result"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_migrate_entry_converts_time_values_to_seconds(hass):
    """Migration should normalize time period fields to integer seconds."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=0,
        data={
            climate.CONF_NAME: "Office",
            climate.CONF_HEATER: "switch.heater_office",
            climate.CONF_SENSOR: "sensor.office_temp",
            climate.CONF_KEEP_ALIVE: "00:01:00",
            climate.CONF_MIN_DUR: {"minutes": 2},
        },
    )
    entry.add_to_hass(hass)

    assert await integration.async_migrate_entry(hass, entry)
    assert entry.minor_version == 1
    assert entry.data[climate.CONF_KEEP_ALIVE] == 60
    assert entry.data[climate.CONF_MIN_DUR] == 120
