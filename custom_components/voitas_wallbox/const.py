"""Constants for Voitas Wallbox integration."""

DOMAIN = "voitas_wallbox"
DEFAULT_PORT = 43000
DEFAULT_SCAN_INTERVAL = 1  # seconds

CONF_HOST = "host"
CONF_PORT = "port"
CONF_POWER_SOURCE = "power_source"
CONF_POWER_VALUE = "power_value"
CONF_POWER_ENTITY = "power_entity"

POWER_SOURCE_MANUAL = "manual"
POWER_SOURCE_ENTITY = "entity"

# UDP Protocol fields
# WALLBOX-LD <proto> <uuid> <status> <field4> <max_power_w> <min_current_ma> <interval_ms>
STATUS_IDLE = "idle"
STATUS_CHARGING = "charging"

ATTR_STATUS = "status"
ATTR_UUID = "uuid"
ATTR_MAX_POWER = "max_power_w"
ATTR_PROTOCOL = "protocol_version"
