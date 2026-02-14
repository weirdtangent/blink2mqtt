# weirdtangent/blink2mqtt

Expose multiple [Blink](https://blinkforhome.com) cameras and events via MQTT —
with native [Home Assistant](https://www.home-assistant.io) discovery support.

[![Deploy Status](https://github.com/weirdtangent/blink2mqtt/actions/workflows/deploy.yaml/badge.svg)](https://github.com/weirdtangent/blink2mqtt/actions/workflows/deploy.yaml)

Built on [`blinkpy`](https://github.com/fronzbot/blinkpy).

Based on my forked versions of [amcrest2mqtt](https://github.com/weirdtangent/amcrest2mqtt)
and [govee2mqtt](https://github.com/weirdtangent/govee2mqtt).

A few notes:
* "Rediscover" button added to service - when pressed, device discovery is re-run so HA will rediscover deleted devices

## Docker

For `docker-compose`, use the [configuration included](https://github.com/weirdtangent/blink2mqtt/blob/master/docker-compose.yaml) in this repository.

Using the [docker image](https://hub.docker.com/repository/docker/graystorm/blink2mqtt/general), mount your configuration volume at `/config` and include a `config.yaml` file (see the included [config.yaml.sample](config.yaml.sample) file as a template).

## Configuration

The recommended way to configure blink2mqtt is via the `config.yaml` file. See [config.yaml.sample](config.yaml.sample) for a complete example with all available options.

### MQTT Settings

```yaml
mqtt:
  host: 10.10.10.1
  port: 1883
  username: mqtt
  password: password
  qos: 0
  protocol_version: "5"  # MQTT protocol version: 3.1.1/3 or 5
  prefix: blink2mqtt
  reconnect_delay: 30
  home_assistant: true
  discovery_prefix: homeassistant
  # TLS settings (optional)
  tls_enabled: false
  tls_ca_cert: /config/ca.crt
  tls_cert: /config/client.crt
  tls_key: /config/client.key
```

### Blink Account Settings

```yaml
blink:
  username: email@example.com
  password: password
  device_update_interval: 30     # seconds between device updates
  device_rescan_interval: 3600   # seconds between device list rescans
  snapshot_update_interval: 5    # minutes between camera snapshot refreshes
```

### Other Settings

```yaml
timezone: America/New_York       # Timezone (see TZ database list)
```

### Environment Variables

While the config file is recommended, environment variables are also supported. See [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) for the full list of available environment variables.

## Snapshots/Eventshots plus Home Assistant Area Cards

The `camera` snapshots work really well for the HomeAssistant `Area` cards on a dashboard - just make this MQTT camera device the only camera for an area and place an `Area` card for that location.

An "event snapshot" (`eventshot`) is separately (and specifically, by filename) collected when the camera automatically records a snapshot because of an event.

## Object Detection with vision2mqtt

When enabled, blink2mqtt publishes motion event snapshots to MQTT for AI-powered object detection via [vision2mqtt](https://github.com/weirdtangent/vision2mqtt). Detection results (person, vehicle, animal, bird) are published back to MQTT and auto-discovered by Home Assistant.

This has been specifically tested with the [M5Stack LLM-8850 Pi HAT](https://docs.m5stack.com/en/ai_hardware/LLM-8850_Card) kit on a Raspberry Pi 5, which provides ~8ms/frame inference via the AXera AX8850 NPU (24 TOPS).

### Enable vision requests

In `config.yaml`:
```yaml
vision_request: true
```

Or via environment variable:
```
VISION_REQUEST=true
```

When a motion event occurs, blink2mqtt publishes a JSON message to `blink2mqtt/vision/request` containing the camera snapshot as a base64-encoded image. vision2mqtt subscribes to `+/vision/request`, runs YOLO11 inference, and publishes detection results back to MQTT — including per-camera presence sensors that appear automatically in Home Assistant.

See the [vision2mqtt README](https://github.com/weirdtangent/vision2mqtt) for full setup instructions, including the Raspberry Pi 5 + LLM-8850 hardware setup guide.

## Device Support

The app supports events for any Blink device supported by the [`blinkpy`](https://github.com/fronzbot/blinkpy) library.

## Home Assistant

The app has built-in support for Home Assistant discovery. Set `home_assistant: true` in the mqtt section of your config.yaml (or the `MQTT_HOMEASSISTANT` environment variable to `true`) to enable support.
If you are using a different MQTT prefix to the default, you will need to set the `discovery_prefix` setting (or `MQTT_DISCOVERY_PREFIX` environment variable).

## Running the app

For Docker Compose, see the included [docker-compose.yaml](docker-compose.yaml).

The app expects the config directory to be mounted at `/config`:
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
useful to myself and others, not for any financial gain - but any token of appreciation is much appreciated :)

<a href="https://buymeacoffee.com/weirdtangent">Buy Me A Coffee</a>

---

### Build & Quality Status

![Build & Release](https://img.shields.io/github/actions/workflow/status/weirdtangent/blink2mqtt/deploy.yaml?branch=main&label=build%20%26%20release&logo=githubactions)
![Lint](https://img.shields.io/github/actions/workflow/status/weirdtangent/blink2mqtt/deploy.yaml?branch=main&label=lint%20(ruff%2Fblack%2Fmypy)&logo=python)
![Docker Build](https://img.shields.io/github/actions/workflow/status/weirdtangent/blink2mqtt/deploy.yaml?branch=main&label=docker%20build&logo=docker)
![Python](https://img.shields.io/badge/python-3.12%20|%203.13%20|%203.14-blue?logo=python)
![Release](https://img.shields.io/github/v/release/weirdtangent/blink2mqtt?sort=semver)
![Docker Image Tag](https://img.shields.io/github/v/release/weirdtangent/blink2mqtt?label=docker%20tag&sort=semver&logo=docker)
![Docker Pulls](https://img.shields.io/docker/pulls/graystorm/blink2mqtt?logo=docker)
![License](https://img.shields.io/github/license/weirdtangent/blink2mqtt)

### Security

![SBOM](https://img.shields.io/badge/SBOM-included-green?logo=docker)
![Provenance](https://img.shields.io/badge/provenance-attested-green?logo=sigstore)
![Signed](https://img.shields.io/badge/cosign-signed-green?logo=sigstore)
![Trivy](https://img.shields.io/badge/trivy-scanned-green?logo=aquasecurity)
