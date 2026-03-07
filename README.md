# PID Thermostat

`pid_thermostat` is a Home Assistant custom climate integration that controls a
heater or cooler from a temperature sensor using a PID controller, with optional
autotuning.

## Features

- PID-based temperature control (`kp`, `ki`, `kd`)
- Optional autotune with multiple tuning rules
- Heating mode and cooling mode (`ac_mode`)
- Optional Home/Away presets with separate target temperatures
- Optional minimum relay cycle protection (`min_cycle_duration`)
- Config flow support in Home Assistant UI
- State persistence across restart for:
  - home/away setpoints
  - PID parameters
  - selected autotune mode

## Installation

### HACS (recommended)

1. Open HACS.
2. Add this repository as a custom repository.
3. Install `PID thermostat`.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/pid_thermostat` into your Home Assistant
   `custom_components` directory.
2. Restart Home Assistant.

## Brand Assets (Icon/Logo)

This repository includes local brand assets in:

- `custom_components/pid_thermostat/brand/icon.png`
- `custom_components/pid_thermostat/brand/dark_icon.png`
- `custom_components/pid_thermostat/brand/logo.png`
- `custom_components/pid_thermostat/brand/dark_logo.png`
- `@2x` variants for each of the above

For the icon to be reused broadly across Home Assistant ecosystems (including
HACS catalog rendering paths that rely on the central brands repository), submit
the same assets to `home-assistant/brands` under
`custom_integrations/pid_thermostat/`.

## Configuration

### UI (Config Flow)

1. Go to `Settings` -> `Devices & Services` -> `Add Integration`.
2. Search for `PID thermostat`.
3. Select your `heater` entity and `target_sensor`.
4. Fill in optional tuning values as needed.

### YAML (legacy platform setup)

```yaml
climate:
  - platform: pid_thermostat
    name: Office PID
    heater: switch.office_heater
    target_sensor: sensor.office_temperature
    keep_alive: "00:00:30"
    target_temp: 21.0
    min_temp: 15.0
    max_temp: 25.0
    ac_mode: false
    min_cycle_duration: "00:02:00"
    cold_tolerance: 0.3
    hot_tolerance: 0.3
    initial_hvac_mode: heat
    away_temp: 17.0
    precision: 0.1
    difference: 100
    kp: 0
    ki: 0
    kd: 0
    pwm: 60
    autotune: none
    noiseband: 0.5
```

## Configuration Reference

| Key | Required | Default | Notes |
| --- | --- | --- | --- |
| `heater` | Yes | - | Entity to control. |
| `target_sensor` | Yes | - | Temperature sensor entity. |
| `keep_alive` | Yes | `60s` in UI default | Control interval. |
| `target_temp` | No | Restored or min/max fallback | Initial target temperature. |
| `min_temp` / `max_temp` | No | HA defaults | Climate temperature bounds. |
| `ac_mode` | No | `false` | `false` = heat behavior, `true` = cool behavior. |
| `min_cycle_duration` | No | disabled | Minimum delay between relay state changes. |
| `cold_tolerance` / `hot_tolerance` | No | `0.3` | Temperature tolerance values. |
| `initial_hvac_mode` | No | `off` | Initial mode after startup. |
| `away_temp` | No | - | Enables Home/Away presets when set. |
| `precision` | No | entity default | One of `0.1`, `0.5`, `1.0`. |
| `difference` | No | `100` | PID output span / autotune relay amplitude. |
| `kp`, `ki`, `kd` | No | `0` | PID coefficients. |
| `pwm` | No | `0` | PWM cycle length in seconds (relay mode when > 0). |
| `autotune` | No | `none` | Autotune rule (see list below). |
| `noiseband` | No | `0.5` | Autotune noise band. |

## Autotune Rules

Allowed values for `autotune`:

- `none`
- `ziegler-nichols`
- `tyreus-luyben`
- `ciancone-marlin`
- `pessen-integral`
- `some-overshoot`
- `no-overshoot`
- `brewing`

## Behavior Notes

### `min_cycle_duration`

`min_cycle_duration` applies to relay-style ON/OFF transitions only.
The integration enforces this delay using the heater entity's actual transition
time, including external/manual toggles. Calls executed with `force=True`
intentionally bypass this guard.

### HVAC mode validation

The entity rejects unsupported mode changes for its configuration:

- Heat-configured thermostat: `heat` and `off`
- Cool-configured thermostat: `cool` and `off`

### Sensor updates

When the sensor updates, the thermostat recalculates control output immediately
and still respects `min_cycle_duration` for relay toggles.

## Persistence Across Restarts

The integration restores these values from the previous entity state:

- current target temperature
- home temperature (`home_temp`)
- away temperature (`away_temp`)
- PID parameters (`pid_kp`, `pid_ki`, `pid_kd`)
- autotune mode (`autotune_mode`)

## Standard Climate Services

Use standard Home Assistant climate services such as:

- `climate.set_temperature`
- `climate.set_hvac_mode`
- `climate.set_preset_mode`
- `climate.turn_on`
- `climate.turn_off`

## Development

Run tests:

```bash
pytest -q
```
