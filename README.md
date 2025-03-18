# weirdtangent/blink2mqtt

Expose multiple Blink cameras and events to an MQTT broker, primarily
designed to work with Home Assistant. A WIP, since I'm new to Python.
Uses the [`blinkpy`](https://github.com/fronzbot/blinkpy) library.

Based on my forked versions of [amcrest2mqtt](https://github.com/weirdtangent/amcrest2mqtt)
and [govee2mqtt](https://github.com/weirdtangent/govee2mqtt).

You can define config in config.yaml and pass `-c path/to/config.yaml`. See the
`config.yaml.sample` file for an example.

Or, we support the following environment variables and defaults (though, this is becoming unwieldy):

-   `BLINK_HOSTS` (required, 1+ space-separated list of hostnames/ips)
-   `BLINK_NAMES` (required, 1+ space-separated list of device names - must match count of BLINK_HOSTS)
-   `BLINK_PORT` (optional, default = 80)
-   `BLINK_USERNAME` (optional, default = admin)
-   `BLINK_PASSWORD` (required)

-   `MQTT_USERNAME` (required)
-   `MQTT_PASSWORD` (optional, default = empty password)
-   `MQTT_HOST` (optional, default = 'localhost')
-   `MQTT_QOS` (optional, default = 0)
-   `MQTT_PORT` (optional, default = 1883)
-   `MQTT_TLS_ENABLED` (required if using TLS) - set to `true` to enable
-   `MQTT_TLS_CA_CERT` (required if using TLS) - path to the ca certs
-   `MQTT_TLS_CERT` (required if using TLS) - path to the private cert
-   `MQTT_TLS_KEY` (required if using TLS) - path to the private key
-   `MQTT_PREFIX` (optional, default = amgrest2mqtt)
-   `MQTT_HOMEASSISTANT` (optional, default = true)
-   `MQTT_DISCOVERY_PREFIX` (optional, default = 'homeassistant')

-   `TZ` (required, timezone identifier, see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#List)
-   `STORAGE_UPDATE_INTERVAL` (optional, default = 900) - how often to fetch storage stats (in seconds)
-   `SNAPSHOT_UPDATE_INTERVAL` (optional, default = 60) - how often to fetch camera snapshot (in seconds)

It exposes through device discovery a `service` and a `device` with components for each camera:

-   `homeassistant/device/blink-service` - service config

-   `homeassistant/device/blink-[SERIAL_NUMBER]` per camera, with components:
-    `event`            - most all "other" events, not exposed below
-    `camera`           - a snapshot is saved every SNAPSHOT_UPDATE_INTERVAL (also based on how often camera saves snapshot image), also an "eventshot" is stored at the time an "event" is triggered in the camera. This is collected by filename, when the Blink camera logs a snapshot was saved because of an event (rather than just a routine timed snapshot)
-    `doorbell`         - doorbell status
-    `human`            - human detection
-    `motion`           - motion events (if supported)
-    `config`           - device configuration information
-    `privacy_mode`     - get (and set) the privacy mode switch of the camera
-    `motion_detection` - get (and set) the motion detection switch of the camera

## Snapshots/Eventshots plus Home Assistant Area Cards

The `camera` snapshots work really well for the HomeAssistant `Area` cards on a dashboard - just make this MQTT camera device the only camera for an area and place an `Area` card for that location.

An "event snapshot" (`eventshot`) is separately (and specifically, by filename) collected when the camera automatically records a snapshot because of an event.

## Device Support

The app supports events for any Blink device supported by the [`blinkpy`](https://github.com/fronzbot/blinkpy) library.

## Home Assistant

The app has built-in support for Home Assistant discovery. Set the `MQTT_HOMEASSISTANT` environment variable to `true` to enable support.
If you are using a different MQTT prefix to the default, you will need to set the `MQTT_DISCOVERY_PREFIX` environment variable.

## Running the app

To run via env variables with Docker Compose, see docker-compose.yaml
or make sure you attach a volume with the config file and point to that directory, for example:
```
CMD [ "python", "./app.py", "-c", "/config" ]
```

## Out of Scope

### Non-Docker Environments

Docker is the only supported way of deploying the application. The app should run directly via Python but this is not supported.

## Buy Me A Coffee

A few people have kindly requested a way to donate a small amount of money. If you feel so inclined I've set up a "Buy Me A Coffee"
page where you can donate a small sum. Please do not feel obligated to donate in any way - I work on the app because it's
useful to myself and others, not for any financial gain - but any token of appreciation is much appreciated 🙂

<a href="https://buymeacoffee.com/weirdtangent">Buy Me A Coffee</a>

### How Happy am I?

<img src="https://github.com/weirdtangent/blink2mqtt/actions/workflows/deploy.yaml/badge.svg" />
