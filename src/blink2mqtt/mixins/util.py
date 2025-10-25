# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import os
import logging
import pathlib
import yaml
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.core import Blink2Mqtt
    from blink2mqtt.interface import BlinkServiceProtocol

READY_FILE = os.getenv("READY_FILE", "/tmp/blink2mqtt.ready")


class UtilMixin:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    def mark_ready(self: Blink2Mqtt):
        pathlib.Path(READY_FILE).touch()

    def heartbeat_ready(self: Blink2Mqtt):
        pathlib.Path(READY_FILE).touch()

    def read_file(self: Blink2Mqtt, file_name):
        try:
            with open(file_name, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_name}")

    def load_config(self: Blink2Mqtt, config_arg=None):
        version = os.getenv("BLINK2MQTT_VERSION", self.read_file("VERSION"))
        config_from = "env"
        config = {}

        # Determine config file path
        config_path = config_arg or "/config"
        config_path = os.path.expanduser(config_path)
        config_path = os.path.abspath(config_path)

        if os.path.isdir(config_path):
            config_file = os.path.join(config_path, "config.yaml")
        elif os.path.isfile(config_path):
            config_file = config_path
            config_path = os.path.dirname(config_file)
        else:
            # If it's not a valid path but looks like a filename, handle gracefully
            if config_path.endswith(".yaml"):
                config_file = config_path
            else:
                config_file = os.path.join(config_path, "config.yaml")

        # Try to load from YAML
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    config = yaml.safe_load(f) or {}
                config_from = "file"
            except Exception as e:
                logging.warning(f"Failed to load config from {config_file}: {e}")
        else:
            logging.warning(
                f"Config file not found at {config_file}, falling back to environment vars"
            )

        # Merge with environment vars (env vars override nothing if file exists)
        mqtt = config.get("mqtt", {})
        blink = config.get("blink", {})

        mqtt = {
            "host": mqtt.get("host") or os.getenv("MQTT_HOST", "localhost"),
            "port": int(mqtt.get("port") or os.getenv("MQTT_PORT", 1883)),
            "qos": int(mqtt.get("qos") or os.getenv("MQTT_QOS", 0)),
            "username": mqtt.get("username") or os.getenv("MQTT_USERNAME", ""),
            "password": mqtt.get("password") or os.getenv("MQTT_PASSWORD", ""),
            "tls_enabled": mqtt.get("tls_enabled")
            or (os.getenv("MQTT_TLS_ENABLED", "false").lower() == "true"),
            "tls_ca_cert": mqtt.get("tls_ca_cert") or os.getenv("MQTT_TLS_CA_CERT"),
            "tls_cert": mqtt.get("tls_cert") or os.getenv("MQTT_TLS_CERT"),
            "tls_key": mqtt.get("tls_key") or os.getenv("MQTT_TLS_KEY"),
            "prefix": mqtt.get("prefix") or os.getenv("MQTT_PREFIX", "blink2mqtt"),
            "discovery_prefix": mqtt.get("discovery_prefix")
            or os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"),
        }

        blink = {
            "username": blink.get("username") or os.getenv("BLINK_USERNAME") or "admin",
            "password": blink.get("password") or os.getenv("BLINK_PASSWORD") or "",
            "device_interval": int(
                blink.get("device_update_interval")
                or os.getenv("BLINK_DEVICE_UPDATE_INTERVAL", 30)
            ),
            "device_list_interval": int(
                blink.get("device_rescan_interval")
                or os.getenv("BLINK_RESCAN_INTERVAL", 3600)
            ),
            "snapshot_update_interval": int(
                blink.get("snapshot_update_interval")
                or os.getenv("SNAPSHOT_UPDATE_INTERVAL", 900)
            ),
        }

        config = {
            "mqtt": mqtt,
            "blink": blink,
            "debug": config.get("debug", os.getenv("DEBUG", "").lower() == "true"),
            "hide_ts": config.get(
                "hide_ts", os.getenv("HIDE_TS", "").lower() == "true"
            ),
            "timezone": config.get("timezone", os.getenv("TZ", "UTC")),
            "config_from": config_from,
            "config_path": config_path,
            "version": version,
        }

        # Validate required fields
        if not config["blink"].get("username"):
            raise ValueError(
                "`blink.username` required in config file or BLINK_USERNAME env var"
            )

        return config
