# Smart Thermostat

Uses PID to control thermostats

## min_cycle_duration behavior

`min_cycle_duration` applies to relay-style ON/OFF transitions only.
The thermostat enforces this delay between state changes based on the heater
entity's last transition time, including external/manual toggles. Operations
executed with `force=True` intentionally bypass this guard.
