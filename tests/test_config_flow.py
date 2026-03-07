"""Tests for pid_thermostat config flow and migrations."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.pid_thermostat as integration
from custom_components.pid_thermostat import climate, const

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
async def test_user_config_flow_rejects_missing_required_entity_fields(hass):
    """Config flow should reject submissions missing required selector fields."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["type"] == FlowResultType.FORM

    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                climate.CONF_NAME: "Office",
                const.CONF_SENSOR: "sensor.office_temp",
                const.CONF_KEEP_ALIVE: 45,
                const.CONF_AUTOTUNE: const.DEFAULT_AUTOTUNE,
            },
        )


@pytest.mark.asyncio
async def test_user_config_flow_rejects_invalid_entity_selector_values(hass):
    """Config flow should reject invalid entity selector values."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["type"] == FlowResultType.FORM

    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                climate.CONF_NAME: "Office",
                const.CONF_HEATER: 123,
                const.CONF_SENSOR: "sensor.office_temp",
                const.CONF_KEEP_ALIVE: 45,
                const.CONF_AUTOTUNE: const.DEFAULT_AUTOTUNE,
            },
        )


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


@pytest.mark.asyncio
async def test_import_flow_creates_entry_and_normalizes_time_values(hass):
    """Import flow should normalize YAML-like timing values to entry format."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "import"},
        data={
            climate.CONF_HEATER: "switch.heater_office",
            climate.CONF_SENSOR: "sensor.office_temp",
            climate.CONF_KEEP_ALIVE: timedelta(seconds=45),
            climate.CONF_MIN_DUR: timedelta(seconds=120),
            climate.CONF_AUTOTUNE: climate.DEFAULT_AUTOTUNE,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][climate.CONF_KEEP_ALIVE] == 45
    assert result["data"][climate.CONF_MIN_DUR] == 120
    assert result["data"][climate.CONF_NAME] == climate.DEFAULT_NAME


@pytest.mark.asyncio
async def test_options_flow_updates_runtime_parameters(hass):
    """Options flow should allow editing thermostat tuning parameters."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Office",
        data={
            climate.CONF_NAME: "Office",
            climate.CONF_HEATER: "switch.heater_office",
            climate.CONF_SENSOR: "sensor.office_temp",
            climate.CONF_KEEP_ALIVE: 45,
            climate.CONF_KP: 1.0,
            climate.CONF_AUTOTUNE: climate.DEFAULT_AUTOTUNE,
        },
        unique_id="switch.heater_office::sensor.office_temp",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            climate.CONF_NAME: "Office Tuned",
            climate.CONF_KEEP_ALIVE: 90,
            climate.CONF_KP: 6.0,
            climate.CONF_AUTOTUNE: climate.DEFAULT_AUTOTUNE,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][climate.CONF_KEEP_ALIVE] == 90
    assert result["data"][climate.CONF_KP] == 6.0
