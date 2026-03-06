"""The pid_thermostat component."""

from __future__ import annotations

from typing import Any

import homeassistant.helpers.config_validation as cv
from homeassistant.components.climate.const import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .climate import CONF_KEEP_ALIVE, CONF_MIN_DUR

PLATFORMS = [Platform.CLIMATE]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration from YAML."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up pid_thermostat from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _migrate_time_field(data: dict[str, Any], key: str) -> bool:
    """Convert time period fields to integer seconds for config entries."""
    value = data.get(key)
    if value is None or isinstance(value, int):
        return False

    if isinstance(value, float):
        data[key] = int(value)
        return True

    try:
        data[key] = int(cv.time_period(value).total_seconds())
    except Exception:  # pragma: no cover - defensive migration guard
        return False
    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to the latest format."""
    if config_entry.version > 1:
        return False

    if config_entry.version == 1 and config_entry.minor_version < 1:
        new_data = dict(config_entry.data)
        changed = False
        changed |= _migrate_time_field(new_data, CONF_KEEP_ALIVE)
        changed |= _migrate_time_field(new_data, CONF_MIN_DUR)

        hvac_mode = new_data.get("initial_hvac_mode")
        if isinstance(hvac_mode, HVACMode):
            new_data["initial_hvac_mode"] = hvac_mode.value
            changed = True

        if changed or config_entry.minor_version != 1:
            hass.config_entries.async_update_entry(
                config_entry,
                data=new_data,
                version=1,
                minor_version=1,
            )

    return True
