# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from deepmerge import Merger
import logging
import os
import pathlib
from typing import TYPE_CHECKING, Any
import yaml

if TYPE_CHECKING:
    from blink2mqtt.core import Blink2Mqtt
    from blink2mqtt.interface import BlinkServiceProtocol

READY_FILE = os.getenv("READY_FILE", "/tmp/blink2mqtt.ready")


class HelpersMixin:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    def build_camera_states(self: Blink2Mqtt, device_id: str, camera: list[str, str]) -> None:
        self.upsert_state(
            device_id,
            switch={
                "motion_detection": "ON" if camera["motion_detection"] else "OFF",
            },
            sensor={
                "battery_status": camera["battery"],
                "temperature": camera["temperature"],
                "wifi_signal": camera["wifi_strength"],
                "last_event": "",
                "last_event_time": "",
            },
            binary_sensor={
                "motion": camera["motion"],
            },
        )

    def build_sync_module_states(self: Blink2Mqtt, device_id: str, sync_module: list[str, str]) -> None:
        self.upsert_state(
            device_id,
            switch={"armed": "ON" if sync_module["arm_mode"] else "OFF"},
            sensor={"local_storage": sync_module["local_storage"]},
        )

    # send command to Blink -----------------------------------------------------------------------

    async def handle_device_command(self: Blink2Mqtt, device_id: str, handler: str, message: str) -> None:
        match handler:
            case "motion_detection":
                was = self.states[device_id]["sensor"][handler]
                self.upsert_state(device_id, switch={"motion_detection": message})
                self.logger.info(f"sending {device_id} motion_detection to {message} command to Blink")
                self.publish_device_state(device_id)
                success = await self.set_motion_detection(device_id, "ON" if message else "OFF")
                if not success:
                    self.logger.error(f"setting {device_id} motion_detection to {message} failed")
                    self.upsert_state(device_id, switch={"motion_detection": was})
                    self.publish_device_state(device_id)
            case _:
                self.logger.error(f"Received command for unknown: {handler} with payload {message}")

    def handle_service_command(self: Blink2Mqtt, handler: str, message: str) -> None:
        match handler:
            case "device_update_interval":
                self.device_interval = message
                self.logger.debug(f"device_interval updated to be {message}")
            case "device_rescan_interval":
                self.device_list_interval = message
                self.logger.debug(f"device_list_interval updated to be {message}")
            case "snapshot_update_interval":
                self.snapshot_update_interval = message
                self.logger.debug(f"snapshot_update_interval updated to be {message}")
            case "refresh_device_list":
                if message == "refresh":
                    self.rediscover_all()
                else:
                    self.logger.error("[handler] unknown [message]")
                    return
            case _:
                self.logger.error(f"Unrecognized message to {handler} -> {message}")
                return
        self.publish_service_state()

    def rediscover_all(self: Blink2Mqtt) -> None:
        self.publish_service_state()
        self.publish_service_discovery()
        for device_id in self.devices:
            if device_id == "service":
                continue
            self.publish_device_state(device_id)
            self.publish_device_discovery(device_id)

    # utilities -----------------------------------------------------------------------------------

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
            logging.warning(f"Config file not found at {config_file}, falling back to environment vars")

        # Merge with environment vars (env vars override nothing if file exists)
        mqtt = config.get("mqtt", {})
        blink = config.get("blink", {})

        # fmt: off
        mqtt = {
            "host":             mqtt.get("host")             or os.getenv("MQTT_HOST", "localhost"),
            "port":         int(mqtt.get("port")             or os.getenv("MQTT_PORT", 1883)),
            "qos":          int(mqtt.get("qos")              or os.getenv("MQTT_QOS", 0)),
            "username":         mqtt.get("username")         or os.getenv("MQTT_USERNAME", ""),
            "password":         mqtt.get("password")         or os.getenv("MQTT_PASSWORD", ""),
            "tls_enabled":      mqtt.get("tls_enabled")      or (os.getenv("MQTT_TLS_ENABLED", "false").lower() == "true"),
            "tls_ca_cert":      mqtt.get("tls_ca_cert")      or os.getenv("MQTT_TLS_CA_CERT"),
            "tls_cert":         mqtt.get("tls_cert")         or os.getenv("MQTT_TLS_CERT"),
            "tls_key":          mqtt.get("tls_key")          or os.getenv("MQTT_TLS_KEY"),
            "prefix":           mqtt.get("prefix")           or os.getenv("MQTT_PREFIX", "blink2mqtt"),
            "discovery_prefix": mqtt.get("discovery_prefix") or os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"),
        }

        blink = {
            "username":                     blink.get("username")                 or os.getenv("BLINK_USERNAME") or "admin",
            "password":                     blink.get("password")                 or os.getenv("BLINK_PASSWORD") or "",
            "device_interval":          int(blink.get("device_update_interval")   or os.getenv("DEVICE_UPDATE_INTERVAL", 30)),
            "device_list_interval":     int(blink.get("device_rescan_interval")   or os.getenv("DEVICE_RESCAN_INTERVAL", 3600)),
            "snapshot_update_interval": int(blink.get("snapshot_update_interval") or os.getenv("SNAPSHOT_UPDATE_INTERVAL", 900)),
        }

        config = {
            "mqtt": mqtt,
            "blink": blink,
            "debug": config.get("debug", os.getenv("DEBUG", "").lower() == "true"),
            "timezone": config.get("timezone", os.getenv("TZ", "UTC")),
            "config_from": config_from,
            "config_path": config_path,
            "version": version,
        }
        # fmt: on

        # Validate required fields
        if not config["blink"].get("username"):
            raise ValueError("`blink.username` required in config file or BLINK_USERNAME env var")

        return config

    # Upsert devices and states -------------------------------------------------------------------

    MERGER = Merger(
        [(dict, "merge"), (list, "append_unique"), (set, "union")],
        ["override"],  # type conflicts: new wins
        ["override"],  # fallback
    )

    def _assert_no_tuples(self: Blink2Mqtt, data, path="root"):
        """Recursively check for tuples in both keys and values of dicts/lists."""
        if isinstance(data, tuple):
            raise TypeError(f"⚠️ Found tuple at {path}: {data!r}")

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(key, tuple):
                    raise TypeError(f"⚠️ Found tuple key at {path}: {key!r}")
                self._assert_no_tuples(value, f"{path}.{key}")
        elif isinstance(data, list):
            for idx, value in enumerate(data):
                self._assert_no_tuples(value, f"{path}[{idx}]")

    def upsert_device(self: Blink2Mqtt, device_id: str, **kwargs: dict[str, Any] | str | int | bool) -> None:
        for section, data in kwargs.items():
            # Pre-merge check
            self._assert_no_tuples(data, f"device[{device_id}].{section}")
            merged = self.MERGER.merge(self.devices.get(device_id, {}), {section: data})
            # Post-merge check
            self._assert_no_tuples(merged, f"device[{device_id}].{section} (post-merge)")
            self.devices[device_id] = merged

    def upsert_state(self: Blink2Mqtt, device_id, **kwargs: dict[str, Any] | str | int | bool) -> None:
        for section, data in kwargs.items():
            self._assert_no_tuples(data, f"state[{device_id}].{section}")
            merged = self.MERGER.merge(self.states.get(device_id, {}), {section: data})
            self._assert_no_tuples(merged, f"state[{device_id}].{section} (post-merge)")
            self.states[device_id] = merged
