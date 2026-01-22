# Environment Variables

While using a config.yaml file is the recommended approach, blink2mqtt also supports configuration via environment variables.

## Blink Account Settings

- `BLINK_USERNAME` (required) - Blink account email address
- `BLINK_PASSWORD` (required) - Blink account password

## Blink Update Intervals

- `DEVICE_UPDATE_INTERVAL` (optional, default = 30) - seconds between device updates
- `DEVICE_RESCAN_INTERVAL` (optional, default = 3600) - seconds between device list rescans
- `SNAPSHOT_UPDATE_INTERVAL` (optional, default = 5) - minutes between camera snapshot refreshes

## MQTT Settings

- `MQTT_HOST` (optional, default = 'localhost') - MQTT broker hostname or IP
- `MQTT_PORT` (optional, default = 1883) - MQTT broker port
- `MQTT_USERNAME` (required) - MQTT username
- `MQTT_PASSWORD` (optional, default = empty password) - MQTT password
- `MQTT_QOS` (optional, default = 0) - Quality of Service (0-2)
- `MQTT_PROTOCOL_VERSION` (optional, default = '5') - MQTT protocol version: '3.1.1' or '5'
- `MQTT_RECONNECT_DELAY` (optional, default = 30) - seconds to wait before reconnecting after failure
- `MQTT_PREFIX` (optional, default = 'blink2mqtt') - MQTT topic prefix

## MQTT TLS Settings

- `MQTT_TLS_ENABLED` (required if using TLS) - set to `true` to enable
- `MQTT_TLS_CA_CERT` (required if using TLS) - path to the CA certificate
- `MQTT_TLS_CERT` (required if using TLS) - path to the client certificate
- `MQTT_TLS_KEY` (required if using TLS) - path to the client private key

## Home Assistant Discovery

- `MQTT_HOMEASSISTANT` (optional, default = 'true') - enable Home Assistant discovery
- `MQTT_DISCOVERY_PREFIX` (optional, default = 'homeassistant') - MQTT discovery topic prefix

## Other Settings

- `TZ` (required) - Timezone (see [TZ database list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#List))
