# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from deepmerge.merger import Merger
import logging
import os
import pathlib
import signal
import threading
from types import FrameType
from typing import TYPE_CHECKING, Any, cast
import yaml

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt

READY_FILE = os.getenv("READY_FILE", "/tmp/blink2mqtt.ready")


class ConfigError(ValueError):
    """Raised when the configuration file is invalid."""

    pass


class HelpersMixin:
    async def build_camera_states(self: Blink2Mqtt, device_id: str, device: dict[str, str]) -> None:
        await self.blink.refresh()

        # update states for cameras
        if device_id in self.blink_cameras:
            device = self.blink_cameras[device_id]
            nightvision = await self.get_nightvision(device_id) if self.blink_cameras[device_id]["supports_get_config"] else ""
            self.upsert_state(
                device_id,
                sensor={
                    "battery_status": device["battery"],
                    "temperature": device["temperature"],
                    "wifi_signal": device["wifi_strength"],
                },
                binary_sensor={
                    "motion": device["motion"],
                },
                switch={"motion_detection": "ON" if device["motion_detection"] else "OFF"},
                select={"nightvision": nightvision},
            )
        # update states for sync modules
        elif device_id in self.blink_sync_modules:
            device = self.blink_sync_modules[device_id]
            self.upsert_state(
                device_id,
                switch={"motion_detection": "ON" if device["motion_detection"] else "OFF"},
                sensor={"local_storage": device["local_storage"]},
            )

    async def build_sync_module_states(self: Blink2Mqtt, device_id: str, sync_module: dict[str, str]) -> None:
        self.upsert_state(
            device_id,
            switch={"armed": "ON" if sync_module["arm_mode"] else "OFF"},
            sensor={"local_storage": sync_module["local_storage"]},
        )

    # send command to Blink -----------------------------------------------------------------------

    async def handle_device_command(self: Blink2Mqtt, device_id: str, handler: str, message: Any) -> None:
        match handler:
            case "motion_detection":
                self.logger.debug(f"sending {device_id} motion_detection to {message} command to Blink")
                success = await self.set_motion_detection(device_id, message == "ON")
                if success:
                    self.upsert_state(device_id, switch={"motion_detection": message})
                    await self.publish_device_state(device_id, "switch", "motion_detection")
            case "nightvision":
                self.logger.debug(f"sending {device_id} nightvision to {message} command to Blink")
                success = await self.set_nightvision(device_id, message)
                if success:
                    self.upsert_state(device_id, select={"nightvision": message})
                    await self.publish_device_state(device_id)

            case _:
                self.logger.error(f"received command for unknown: {handler} with payload {message}")

    async def handle_service_command(self: Blink2Mqtt, handler: str, message: Any) -> None:
        match handler:
            case "refresh_interval":
                self.device_interval = int(message)
                self.logger.info(f"refresh_interval updated to be {message}")
            case "rescan_interval":
                self.device_list_interval = int(message)
                self.logger.info(f"rescan_interval updated to be {message}")
            case "snapshot_interval":
                self.snapshot_update_interval = int(message)
                self.logger.info(f"snapshot_interval updated to be {message}")
            case _:
                self.logger.error(f"unrecognized message to {handler} -> {message}")
                return
        await self.publish_service_state()

    async def rediscover_all(self: Blink2Mqtt) -> None:
        await self.publish_service_state()
        await self.publish_service_discovery()
        for device_id in self.devices:
            await self.publish_device_state(device_id)
            await self.publish_device_discovery(device_id)

    # utilities -----------------------------------------------------------------------------------

    def handle_signal(self: Blink2Mqtt, signum: int, frame: FrameType | None) -> Any:
        sig_name = signal.Signals(signum).name
        self.logger.warning(f"{sig_name} received - stopping service loop")
        self.running = False

        def _force_exit() -> None:
            self.logger.warning("force-exiting process after signal")
            os._exit(0)

        threading.Timer(5.0, _force_exit).start()

    def mark_ready(self: Blink2Mqtt) -> None:
        pathlib.Path(READY_FILE).touch()

    def heartbeat_ready(self: Blink2Mqtt) -> None:
        pathlib.Path(READY_FILE).touch()

    def read_file(self: Blink2Mqtt, file_name: str) -> str:
        try:
            with open(file_name, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_name}")

    def load_config(self: Blink2Mqtt, config_arg: Any | None = None) -> dict[str, Any]:
        version = os.getenv("APP_VERSION", self.read_file("VERSION"))
        tier = os.getenv("APP_TIER", "prod")
        if tier == "dev":
            version += ":DEV"

        config_from = "env"
        config: dict[str, str | bool | int | dict] = {}

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
            except Exception as err:
                logging.warning(f"Failed to load config from {config_file}: {err}")
        else:
            logging.warning(f"Config file not found at {config_file}, falling back to environment vars")

        # Merge with environment vars (env vars override nothing if file exists)
        mqtt = cast(dict[str, Any], config.get("mqtt", {}))
        blink = cast(dict[str, Any], config.get("blink", {}))

        # fmt: off
        mqtt = {
            "host":         cast(str, mqtt.get("host"))            or os.getenv("MQTT_HOST", "localhost"),
            "port":     int(cast(str, mqtt.get("port")             or os.getenv("MQTT_PORT", 1883))),
            "qos":      int(cast(str, mqtt.get("qos")              or os.getenv("MQTT_QOS", 0))),
            "username":               mqtt.get("username")         or os.getenv("MQTT_USERNAME", ""),
            "password":               mqtt.get("password")         or os.getenv("MQTT_PASSWORD", ""),
            "tls_enabled":            mqtt.get("tls_enabled")      or (os.getenv("MQTT_TLS_ENABLED", "false").lower() == "true"),
            "tls_ca_cert":            mqtt.get("tls_ca_cert")      or os.getenv("MQTT_TLS_CA_CERT"),
            "tls_cert":               mqtt.get("tls_cert")         or os.getenv("MQTT_TLS_CERT"),
            "tls_key":                mqtt.get("tls_key")          or os.getenv("MQTT_TLS_KEY"),
            "prefix":                 mqtt.get("prefix")           or os.getenv("MQTT_PREFIX", "blink2mqtt"),
            "discovery_prefix":       mqtt.get("discovery_prefix") or os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"),
        }

        blink = {
            "username":                               blink.get("username")                 or os.getenv("BLINK_USERNAME") or "admin",
            "password":                               blink.get("password")                 or os.getenv("BLINK_PASSWORD") or "",
            "device_interval":          int(cast(str, blink.get("device_update_interval")   or os.getenv("DEVICE_UPDATE_INTERVAL", 30))),
            "device_list_interval":     int(cast(str, blink.get("device_rescan_interval")   or os.getenv("DEVICE_RESCAN_INTERVAL", 3600))),
            "snapshot_update_interval": int(cast(str, blink.get("snapshot_update_interval") or os.getenv("SNAPSHOT_UPDATE_INTERVAL", 5))),
        }

        config = {
            "mqtt":        mqtt,
            "blink":       blink,
            "debug":       str(config.get("debug") or os.getenv("DEBUG", "")).lower() == "true",
            "timezone":    config.get("timezone", os.getenv("TZ", "UTC")),
            "config_from": config_from,
            "config_path": config_path,
            "version":     version,
        }
        # fmt: on

        # Migrate snapshot interval to minutes
        if blink["snapshot_update_interval"] > 60:
            blink["snapshot_update_interval"] = int(blink["snapshot_update_interval"] / 60)

        # Validate required fields
        if not cast(dict, config["blink"]).get("username"):
            raise ConfigError("`blink.username` required in config file or BLINK_USERNAME env var")

        return config

    # Device properties ---------------------------------------------------------------------------

    def get_device_name(self: Blink2Mqtt, device_id: str) -> str:
        return cast(str, self.devices[device_id]["component"]["device"]["name"])

    def get_component(self: Blink2Mqtt, device_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self.devices[device_id]["component"])

    def get_platform(self: Blink2Mqtt, device_id: str) -> str:
        return cast(str, self.devices[device_id]["component"].get("platform", "unknown"))

    def is_discovered(self: Blink2Mqtt, device_id: str) -> bool:
        if "internal" not in self.states[device_id]:
            return False
        return cast(bool, self.states[device_id]["internal"].get("discovered", False))

    def get_device_state_topic(self: Blink2Mqtt, device_id: str, mode_name: str = "") -> str:
        component = self.get_component(device_id)["cmps"][f"{device_id}_{mode_name}"] if mode_name else self.get_component(device_id)

        match component["platform"]:
            case "camera":
                return cast(str, component["topic"])
            case "image":
                return cast(str, component["image_topic"])
            case _:
                return cast(str, component.get("stat_t") or component.get("state_topic"))

    def get_device_image_topic(self: Blink2Mqtt, device_id: str) -> str:
        component = self.get_component(device_id)
        return cast(str, component["topic"])

    def get_device_availability_topic(self: Blink2Mqtt, device_id: str) -> str:
        component = self.get_component(device_id)
        return cast(str, component.get("avty_t") or component.get("availability_topic"))

    # Upsert devices and states -------------------------------------------------------------------

    def _assert_no_tuples(self: Blink2Mqtt, data: Any, path: str = "root") -> None:
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

    def upsert_device(self: Blink2Mqtt, device_id: str, **kwargs: dict[str, Any] | str | int | bool | None) -> bool:
        MERGER = Merger(
            [(dict, "merge"), (list, "append_unique"), (set, "union")],
            ["override"],  # type conflicts: new wins
            ["override"],  # fallback
        )
        prev = self.devices.get(device_id, {})
        for section, data in kwargs.items():
            # Pre-merge check
            self._assert_no_tuples(data, f"device[{device_id}].{section}")
            merged = MERGER.merge(self.devices.get(device_id, {}), {section: data})
            # Post-merge check
            self._assert_no_tuples(merged, f"device[{device_id}].{section} (post-merge)")
            self.devices[device_id] = merged
        new = self.devices.get(device_id, {})
        return False if prev == new else True

    def upsert_state(self: Blink2Mqtt, device_id: str, **kwargs: dict[str, Any] | str | int | bool | None) -> bool:
        MERGER = Merger(
            [(dict, "merge"), (list, "append_unique"), (set, "union")],
            ["override"],  # type conflicts: new wins
            ["override"],  # fallback
        )
        prev = self.states.get(device_id, {})
        for section, data in kwargs.items():
            self._assert_no_tuples(data, f"state[{device_id}].{section}")
            merged = MERGER.merge(self.states.get(device_id, {}), {section: data})
            self._assert_no_tuples(merged, f"state[{device_id}].{section} (post-merge)")
            self.states[device_id] = merged
        new = self.states.get(device_id, {})
        return False if prev == new else True
