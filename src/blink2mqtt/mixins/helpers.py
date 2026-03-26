# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from __future__ import annotations

import asyncio
import base64
from deepmerge.merger import Merger
from datetime import datetime, timedelta
import logging
from mqtt_helper import ConfigError
import os
import pathlib
import re
import signal
import threading
from types import FrameType
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
import yaml

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt

READY_FILE = os.getenv("READY_FILE", "/tmp/blink2mqtt.ready")


class HelpersMixin:
    async def build_camera_states(self: Blink2Mqtt, device_id: str, device: dict[str, str]) -> None:
        # update states for cameras
        if device_id in self.blink_cameras:
            device = self.blink_cameras[device_id]
            prev_clip_count = self.states.get(device_id, {}).get("clip_count", 0)
            new_clip_count = len(device.get("recent_clips") or [])
            nightvision = await self.get_nightvision(device_id) if self.blink_cameras[device_id]["supports_get_config"] else ""
            save_snapshots_default = "ON" if "path" in self.config.get("media", {}) else "OFF"
            current_save = self.states.get(device_id, {}).get("switch", {}).get("save_snapshots")
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
                switch={
                    "motion_detection": "ON" if device["motion_detection"] else "OFF",
                    "save_snapshots": current_save or save_snapshots_default,
                },
                select={"nightvision": nightvision},
                clip_count=new_clip_count,
            )
            # publish vision request when new clips appear (reliable motion indicator)
            self.logger.debug(f"[clip_check] '{self.get_device_name(device_id)}' prev={prev_clip_count} new={new_clip_count} motion={device['motion']}")
            if new_clip_count > prev_clip_count and prev_clip_count > 0:
                self.logger.debug(
                    f"[clip_check] new clips detected for '{self.get_device_name(device_id)}' ({prev_clip_count} -> {new_clip_count}), triggering vision request"
                )
                asyncio.create_task(self._capture_and_publish_vision(device_id))
        # update states for sync modules
        elif device_id in self.blink_sync_modules:
            device = self.blink_sync_modules[device_id]
            self.upsert_state(
                device_id,
                switch={"motion_detection": "ON" if device["motion_detection"] else "OFF"},
                sensor={"local_storage": device["local_storage"]},
            )

    async def _capture_and_publish_vision(self: Blink2Mqtt, device_id: str) -> None:
        """Capture a fresh snapshot from Blink and publish a vision request."""
        name = self.get_device_name(device_id)
        try:
            self.logger.info(f"[_capture_and_publish_vision] starting snapshot capture for '{name}'")
            await self.take_snapshot_from_device(device_id)
            await asyncio.sleep(3)  # Blink needs 2-5 seconds to capture
            await self.blink_refresh()
            snapshot = await self.get_snapshot_from_device(device_id)
            if snapshot:
                self.states[device_id]["snapshot"] = snapshot
                await self.publish_vision_request(device_id, snapshot, "motion_snapshot")
                self.logger.info(f"[_capture_and_publish_vision] published vision request for '{name}'")
            else:
                self.logger.warning(f"[_capture_and_publish_vision] motion detected on '{name}' but failed to get snapshot")
        except Exception as err:
            self.logger.error(f"[_capture_and_publish_vision] failed for '{name}': {err}", exc_info=True)

    async def build_sync_module_states(self: Blink2Mqtt, device_id: str, sync_module: dict[str, str]) -> None:
        self.upsert_state(
            device_id,
            switch={"armed": "ON" if sync_module["arm_mode"] else "OFF"},
            sensor={"local_storage": sync_module["local_storage"]},
        )

    # send command to Blink -----------------------------------------------------------------------

    async def handle_device_command(self: Blink2Mqtt, device_id: str, handler: str, message: Any) -> None:
        match handler:
            case "save_snapshots":
                if message == "ON" and "path" not in self.config.get("media", {}):
                    self.logger.error("user tried to turn on save_snapshots, but there is no media path set")
                    return
                self.upsert_state(device_id, switch={"save_snapshots": message})
                await self.publish_device_state(device_id)
            case "motion_detection":
                self.logger.debug(f"sending '{self.get_device_name(device_id)}' motion_detection to {message} command to Blink")
                success = await self.set_motion_detection(device_id, message == "ON")
                if success:
                    self.upsert_state(device_id, switch={"motion_detection": message})
                    await self.publish_device_state(device_id, "switch", "motion_detection")
            case "nightvision":
                self.logger.debug(f"sending '{self.get_device_name(device_id)}' nightvision to {message} command to Blink")
                success = await self.set_nightvision(device_id, message)
                if success:
                    self.upsert_state(device_id, select={"nightvision": message})
                    await self.publish_device_state(device_id)

            case _:
                self.logger.error(f"received command for unknown: {handler} with payload {message}")

    async def handle_service_command(self: Blink2Mqtt, handler: str, message: Any) -> None:
        try:
            value = int(message)
        except (ValueError, TypeError):
            self.logger.warning(f"invalid non-numeric value for {handler}: {message}")
            return

        match handler:
            case "refresh_interval":
                self.device_interval = max(1, min(900, value))
                self.logger.info(f"refresh_interval updated to {self.device_interval}")
            case "rescan_interval":
                self.device_list_interval = max(1, min(3600, value))
                self.logger.info(f"rescan_interval updated to {self.device_list_interval}")
            case "snapshot_interval":
                self.snapshot_interval_wired_minutes = max(1, min(60, value))
                self.logger.info(f"snapshot_interval updated to {self.snapshot_interval_wired_minutes}")
            case "snapshot_interval_wired_minutes":
                self.snapshot_interval_wired_minutes = max(1, min(60, value))
                self.logger.info(f"snapshot_interval_wired_minutes updated to {self.snapshot_interval_wired_minutes}")
            case "snapshot_interval_battery_hours":
                self.snapshot_interval_battery_hours = max(0, min(60, value))
                self.logger.info(f"snapshot_interval_battery_hours updated to {self.snapshot_interval_battery_hours}")
            case _:
                self.logger.error(f"unrecognized message to {handler} -> {message}")
                return
        await self.publish_service_state()

    async def rediscover_all(self: Blink2Mqtt) -> None:
        await self.publish_service_state()
        await self.publish_service_discovery()
        for device_id in self.devices:
            await self.publish_device_state(device_id, publish_all=True)
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

    def _read_version_file(self: Blink2Mqtt) -> str:
        try:
            with open("VERSION", "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            return "dev"

    def load_config(self: Blink2Mqtt, config_arg: Any | None = None) -> dict[str, Any]:
        def first_value(*values: Any) -> Any:
            for value in values:
                if value is not None and value != "":
                    return value
            return None

        version = os.getenv("APP_VERSION") or self._read_version_file()
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
                with open(config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                config_from = "file"
            except Exception as err:
                logging.warning(f"Failed to load config from {config_file}: {err}")
        else:
            logging.warning(f"Config file not found at {config_file}, falling back to environment vars")

        # Merge with environment vars (env vars override nothing if file exists)
        mqtt = cast(dict[str, Any], config.get("mqtt", {}))
        blink = cast(dict[str, Any], config.get("blink", {}))
        media = cast(dict[str, Any], config.get("media", {}))
        legacy_snapshot_interval = first_value(blink.get("snapshot_update_interval"), os.getenv("SNAPSHOT_UPDATE_INTERVAL"))
        if legacy_snapshot_interval is not None:
            legacy_snapshot_interval = int(legacy_snapshot_interval)
            if legacy_snapshot_interval > 60:
                legacy_snapshot_interval = legacy_snapshot_interval // 60

        # fmt: off
        mqtt = {
            "host":                   cast(str, mqtt.get("host"))                       or os.getenv("MQTT_HOST", "localhost"),
            "port":               int(cast(str, mqtt.get("port")                        or os.getenv("MQTT_PORT", 1883))),
            "protocol_version":   str(cast(str, mqtt.get("protocol_version")            or os.getenv("MQTT_PROTOCOL_VERSION", "5"))),
            "qos":                int(cast(str, mqtt.get("qos")                         or os.getenv("MQTT_QOS", 0))),
            "username":                        mqtt.get("username")                     or os.getenv("MQTT_USERNAME", ""),
            "password":                        mqtt.get("password")                     or os.getenv("MQTT_PASSWORD", ""),
            "tls_enabled":                     mqtt.get("tls_enabled")                  or (os.getenv("MQTT_TLS_ENABLED", "false").lower() == "true"),
            "tls_ca_cert":                     mqtt.get("tls_ca_cert")                  or os.getenv("MQTT_TLS_CA_CERT"),
            "tls_cert":                        mqtt.get("tls_cert")                     or os.getenv("MQTT_TLS_CERT"),
            "tls_key":                         mqtt.get("tls_key")                      or os.getenv("MQTT_TLS_KEY"),
            "prefix":                          mqtt.get("prefix")                       or os.getenv("MQTT_PREFIX", "blink2mqtt"),
            "discovery_prefix":                mqtt.get("discovery_prefix")             or os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"),
        }

        blink = {
            "username":                          first_value(blink.get("username"), os.getenv("BLINK_USERNAME"), "admin"),
            "password":                          first_value(blink.get("password"), os.getenv("BLINK_PASSWORD"), ""),
            "device_interval":        int(cast(str, first_value(blink.get("device_update_interval"), os.getenv("DEVICE_UPDATE_INTERVAL"), 30))),
            "device_list_interval":   int(cast(str, first_value(blink.get("device_rescan_interval"), os.getenv("DEVICE_RESCAN_INTERVAL"), 3600))),
            "snapshot_interval_wired_minutes": int(cast(str, first_value(
                blink.get("snapshot_interval_wired_minutes"),
                os.getenv("SNAPSHOT_INTERVAL_WIRED_MINUTES"),
                legacy_snapshot_interval,
                5,
            ))),
            "snapshot_interval_battery_hours": int(cast(str, first_value(
                blink.get("snapshot_interval_battery_hours"),
                os.getenv("SNAPSHOT_INTERVAL_BATTERY_HOURS"),
                0,
            ))),
        }

        # Determine media path (optional)
        media_path = media.get("path") or os.getenv("MEDIA_PATH")
        if media_path:
            media_path = os.path.expanduser(media_path)
            media_path = os.path.abspath(media_path)

            if os.path.exists(media_path) and os.access(media_path, os.W_OK):
                media["path"] = media_path
                media.setdefault("max_size", int(str(media.get("max_size") or os.getenv("MEDIA_MAX_SIZE", 5))))
                media["retention_days"] = int(str(media.get("retention_days") or os.getenv("MEDIA_RETENTION_DAYS", 7)))
                media.setdefault("media_source", media.get("media_source") or os.getenv("MEDIA_SOURCE", ""))
                logging.info(f"storing snapshots in {media_path} up to {media['max_size']} MB per file")
                if media["retention_days"] > 0:
                    logging.info(f"snapshots will be retained for {media['retention_days']} days")
                else:
                    logging.info("snapshot retention is disabled (retention_days=0). Watch that it doesn't fill up the file system")
            else:
                logging.info("media_path not configured, not found, or is not writable. Will not be saving snapshots")
                media = {}
        else:
            media = {}

        config = {
            "mqtt":             mqtt,
            "blink":            blink,
            "media":            media,
            "debug":            str(config.get("debug") or os.getenv("DEBUG", "")).lower() == "true",
            "timezone":         config.get("timezone", os.getenv("TZ", "UTC")),
            "vision_request":   str(config.get("vision_request") or os.getenv("VISION_REQUEST", "")).lower() == "true",
            "config_from":      config_from,
            "config_path":      config_path,
            "version":          version,
        }
        # fmt: on

        # Validate required fields
        if not cast(dict, config["blink"]).get("username"):
            raise ConfigError("`blink.username` required in config file or BLINK_USERNAME env var")

        return config

    # Device properties ---------------------------------------------------------------------------

    def get_device_name(self: Blink2Mqtt, device_id: str) -> str:
        return cast(str, self.devices[device_id]["component"]["device"]["name"])

    def get_device_name_slug(self: Blink2Mqtt, device_id: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "_", self.get_device_name(device_id).lower())

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

    # Media storage ------------------------------------------------------------------------------

    async def store_snapshot_in_media(self: Blink2Mqtt, device_id: str, image_b64: str) -> str | None:
        media_path = self.config.get("media", {}).get("path")
        if not media_path:
            return None

        # Check save_snapshots switch for this device
        save_on = self.states.get(device_id, {}).get("switch", {}).get("save_snapshots", "OFF")
        if save_on != "ON":
            return None

        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception as err:
            self.logger.error(f"[store_snapshot_in_media] failed to decode image for '{self.get_device_name(device_id)}': {err}")
            return None

        max_size_bytes = self.config["media"].get("max_size", 5) * 1024 * 1024
        if len(image_bytes) > max_size_bytes:
            self.logger.info(f"skipping saving snapshot because {len(image_bytes)} bytes > {max_size_bytes} bytes max")
            return None

        name = self.get_device_name_slug(device_id)
        time = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_name = f"{name}-{time}.jpg"
        file_path = Path(f"{media_path}/{file_name}")

        try:
            file_path.write_bytes(image_bytes)
        except PermissionError as err:
            self.logger.error(f"permission error saving snapshot to {file_path}: {err!r}")
            return None
        except Exception as err:
            self.logger.error(f"failed to save snapshot to {file_path}: {err!r}")
            return None

        # update the latest symlink
        local_file = Path(f"./{file_name}")
        latest_link = Path(f"{media_path}/{name}-latest.jpg")

        try:
            if latest_link.is_symlink():
                latest_link.unlink()
            latest_link.symlink_to(local_file)
        except IOError as err:
            self.logger.error(f"failed to save symlink {latest_link} -> {local_file}: {err!r}")

        self.logger.debug(f"saved snapshot for '{self.get_device_name(device_id)}' to {file_path}")
        return file_name

    async def cleanup_old_snapshots(self: Blink2Mqtt) -> None:
        media_path = self.config.get("media", {}).get("path")
        retention_days = self.config.get("media", {}).get("retention_days", 7)

        if not media_path or retention_days <= 0:
            return

        cutoff = datetime.now() - timedelta(days=retention_days)
        path = Path(media_path)

        for file in path.glob("*.jpg"):
            if file.is_symlink():
                continue

            # Extract timestamp from filename: {name}-YYYYMMDD-HHMMSS.jpg
            match = re.search(r"-(\d{8}-\d{6})\.jpg$", file.name)
            if match:
                file_time = datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
                if file_time < cutoff:
                    try:
                        file.unlink()
                        self.logger.info(f"deleted old snapshot: {file.name}")
                    except Exception as err:
                        self.logger.error(f"failed to delete old snapshot {file.name}: {err!r}")

        # Clean up dangling symlinks (symlinks pointing to deleted files)
        for link in path.glob("*-latest.jpg"):
            if link.is_symlink() and not link.exists():
                try:
                    link.unlink()
                    self.logger.info(f"deleted dangling symlink: {link.name}")
                except Exception as err:
                    self.logger.error(f"failed to delete dangling symlink {link.name}: {err!r}")

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
        if device_id not in self.dirty:
            self.dirty[device_id] = set()
        for section, data in kwargs.items():
            self._assert_no_tuples(data, f"state[{device_id}].{section}")
            merged = MERGER.merge(self.states.get(device_id, {}), {section: data})
            self._assert_no_tuples(merged, f"state[{device_id}].{section} (post-merge)")
            self.states[device_id] = merged
            # track which (section, key) pairs were touched for dicts
            if isinstance(data, dict):
                for k in data:
                    self.dirty[device_id].add((section, k))
            else:
                self.dirty[device_id].add((section, ""))
        new = self.states.get(device_id, {})
        return False if prev == new else True
