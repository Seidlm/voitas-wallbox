"""Constants for Voitas Wallbox integration."""

DOMAIN = "voitas_wallbox"
DEFAULT_PORT = 43000
DEFAULT_SCAN_INTERVAL = 1  # seconds

CONF_HOST = "host"
CONF_PORT = "port"
# Fallback/static kW value — always used when no entity is configured,
# or as fallback when the linked entity is unknown/unavailable.
CONF_POWER_VALUE = "power_value"
# Optional linked entity (e.g. car's charging power sensor). Takes priority
# over the static value whenever it reports a valid numeric state.
CONF_POWER_ENTITY = "power_entity"

DEFAULT_POWER_VALUE = 11.0

# UDP Protocol fields
# WALLBOX-LD <proto> <uuid> <status> <field4> <max_power_w> <min_current_ma> <interval_ms>
STATUS_IDLE = "idle"
STATUS_CHARGING = "charging"

ATTR_STATUS = "status"
ATTR_UUID = "uuid"
ATTR_MAX_POWER = "max_power_w"
ATTR_PROTOCOL = "protocol_version"
