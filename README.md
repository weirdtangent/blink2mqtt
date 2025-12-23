# weirdtangent/blink2mqtt

Expose multiple [Blink](https://blinkforhome.com) cameras and events via MQTT —
with native [Home Assistant](https://www.home-assistant.io) discovery support.

[![Deploy Status](https://github.com/weirdtangent/blink2mqtt/actions/workflows/deploy.yaml/badge.svg)](https://github.com/weirdtangent/blink2mqtt/actions/workflows/deploy.yaml)

Built on [`blinkpy`](https://github.com/fronzbot/blinkpy).

Based on my forked versions of [amcrest2mqtt](https://github.com/weirdtangent/amcrest2mqtt)
and [govee2mqtt](https://github.com/weirdtangent/govee2mqtt).

UPDATE: I've reworked this app almost entirely, as I learn Python (and MQTT and their ingestion by HomeAssistant). v2 completely changes what I was sending for discovery messages and everything is MUCH closer to what HA wants and expects. But also, v2 has had several breaking changes which are cleaned up if you can remove the v1 service and devices from your HomeAssistant AND from your MQTT server (clear them specifically with something like MQTT Explorer; or restart your MQTT service so it loses those old, retained messages. Also, a couple of config/ENV vars have been removed as they were really not necessary (MQTT_HOMEASSISTANT and HIDE_TS). I have many fixes left to do and many features to add (or add back) in. Thanks for being patient for a bit - or I understand you not wanting an app going through so many updates.

A few notes:
* "Rediscover" button added to service - when pressed, device discovery is re-run so HA will rediscover deleted devices

## Docker

docker run -d \
  --name blink2mqtt \
  -v /path/to/config:/config \
  -e MQTT_HOST=mqtt.graystorm.com \
  -e MQTT_USERNAME=hauser \
  -e MQTT_PASSWORD=secret \
  -e BLINK_USERNAME=email@example.com \
  -e BLINK_PASSWORD=blinkpass \
  graystorm/blink2mqtt:latest

For `docker-compose`, use the [configuration included](https://github.com/weirdtangent/blink2mqtt/blob/master/docker-compose.yaml) in this repository.

A docker image is available at `graystorm/blink2mqtt:latest`. You can mount your configuration volume at `/config` (and see the included `config.yaml.sample` file) or use the ENV variables:

### Environment Variables

| Variable | Required | Default | Description |
|-----------|-----------|----------|-------------|
| `BLINK_HOSTS` | ✅ Yes | — | 1+ space-separated list of hostnames/IPs |
| `BLINK_NAMES` | ✅ Yes | — | 1+ space-separated list of device names (must match count of `BLINK_HOSTS`) |
| `BLINK_PORT` | No | `80` | Port for Blink devices |
| `BLINK_USERNAME` | No | `admin` | Username for Blink connection |
| `BLINK_PASSWORD` | ✅ Yes | — | Password for Blink account |
| `MQTT_USERNAME` | ✅ Yes | — | MQTT username |
| `MQTT_PASSWORD` | No | *(empty)* | MQTT password |
| `MQTT_HOST` | No | `localhost` | MQTT broker hostname or IP |
| `MQTT_PORT` | No | `1883` | MQTT broker port |
| `MQTT_QOS` | No | `0` | Quality of Service (0–2) |
| `MQTT_RECONNECT_DELAY` | No | `30` | Seconds to wait before reconnecting after failure |
| `MQTT_TLS_ENABLED` | Conditional | `false` | Enable TLS for MQTT (set to `true`) |
| `MQTT_TLS_CA_CERT` | If TLS | — | Path to CA certificate |
| `MQTT_TLS_CERT` | If TLS | — | Path to client certificate |
| `MQTT_TLS_KEY` | If TLS | — | Path to client private key |
| `MQTT_PREFIX` | No | `blink2mqtt` | MQTT topic prefix |
| `MQTT_HOMEASSISTANT` | No | `true` | Enable Home Assistant discovery |
| `MQTT_DISCOVERY_PREFIX` | No | `homeassistant` | MQTT discovery topic prefix |
| `TZ` | ✅ Yes | — | Timezone (see [TZ database list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#List)) |
| `DEVICE_UPDATE_INTERVAL` | No | `30` | Seconds between device updates |
| `DEVICE_RESCAN_INTERVAL` | No | `3600` | Seconds between device rescans |
| `SNAPSHOT_UPDATE_INTERVAL` | No | `5` | Minutes between snapshot fetches |

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

## What to do about 2FA

If 2FA is required, the container will wait up to 5 minutes for a key.txt file
containing the verification code from Blink. Place this file in your /config directory
when prompted. Once validated, your credentials will be stored for reuse.

## Out of Scope

### Non-Docker Environments

Docker is the only supported way of deploying the application. The app should run directly via Python but this is not supported.

## See also
* [amcrest2mqtt](https://github.com/weirdtangent/amcrest2mqtt)
* [govee2mqtt](https://github.com/weirdtangent/govee2mqtt)

## Buy Me A Coffee

A few people have kindly requested a way to donate a small amount of money. If you feel so inclined I've set up a "Buy Me A Coffee"
page where you can donate a small sum. Please do not feel obligated to donate in any way - I work on the app because it's
useful to myself and others, not for any financial gain - but any token of appreciation is much appreciated 🙂

<a href="https://buymeacoffee.com/weirdtangent">Buy Me A Coffee</a>

---

### Build & Quality Status

![Build & Release](https://img.shields.io/github/actions/workflow/status/weirdtangent/blink2mqtt/deploy.yaml?branch=main&label=build%20%26%20release&logo=githubactions)
![Lint](https://img.shields.io/github/actions/workflow/status/weirdtangent/blink2mqtt/deploy.yaml?branch=main&label=lint%20(ruff%2Fblack%2Fmypy)&logo=python)
![Docker Build](https://img.shields.io/github/actions/workflow/status/weirdtangent/blink2mqtt/deploy.yaml?branch=main&label=docker%20build&logo=docker)
![Python](https://img.shields.io/badge/python-3.12%20|%203.13%20|%203.14-blue?logo=python)
![Release](https://img.shields.io/github/v/release/weirdtangent/blink2mqtt?sort=semver)
![Docker Image Version](https://img.shields.io/docker/v/graystorm/blink2mqtt?sort=semver&logo=docker)
![Docker Pulls](https://img.shields.io/docker/pulls/graystorm/blink2mqtt?logo=docker)
![License](https://img.shields.io/github/license/weirdtangent/blink2mqtt)

### Security

![Trivy Scan](https://img.shields.io/badge/trivy-scanned-success?logo=aquasecurity)
![Cosign](https://img.shields.io/badge/cosign-signed-success?logo=sigstore)
![SBOM](https://img.shields.io/badge/SBOM-included-blue?logo=docker)
![Provenance](https://img.shields.io/badge/provenance-attested-blue?logo=docker)
