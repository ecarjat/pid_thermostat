"""Constants for the pid_thermostat integration."""

DOMAIN = "pid_thermostat"

DEFAULT_TOLERANCE = 0.3
DEFAULT_NAME = "Smart Thermostat"
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
