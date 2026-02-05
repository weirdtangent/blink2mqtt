# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class BlinkMixin:
    async def refresh_device_list(self: Blink2Mqtt) -> None:
        if self.discovery_complete:
            self.logger.info(f"refreshing device list from Blink (every {self.device_list_interval} sec)")
        else:
            self.logger.info("grabbing device list from Blink")

        blink_devices, sync_modules = await asyncio.gather(
            self.get_cameras(),
            self.get_sync_modules(),
        )

        await self.publish_service_state()

        seen_devices: set[str] = set()

        async def build_and_track(device: dict[str, Any]) -> None:
            created = await self.build_component(device)
            if created:
                seen_devices.add(created)

        tasks = [
            *(build_and_track(d) for d in sync_modules.values()),
            *(build_and_track(d) for d in blink_devices.values()),
        ]
        await asyncio.gather(*tasks)

        # Mark missing devices offline
        missing_devices = set(self.devices.keys()) - seen_devices
        for device_id in missing_devices:
            await self.publish_device_availability(device_id, online=False)
            self.logger.warning(f"device '{self.get_device_name(device_id)}' not seen in Blink API list — marked offline")

        # Handle discovery completion
        self.logger.info("first-time device setup and discovery is done")
        self.discovery_complete = True

    # convert Blink device capabilities into MQTT components
    async def build_component(self: Blink2Mqtt, device: dict[str, str]) -> str:
        device_class = self.classify_device(device)
        match device_class:
            case "switch":
                return await self.build_switch(device)
            case "camera":
                return await self.build_camera(device)
        return ""

    def classify_device(self: Blink2Mqtt, device: dict[str, str]) -> str | None:
        device_type = device.get("device_type", None)

        if device_type == "sync_module":
            return "switch"

        # blinkpy already classified this device as a camera (it came from
        # blink.cameras), so trust that regardless of the product_type string.
        # Known product types include: sedona, catalina, owl (Mini), lotus
        # (Doorbell), hawk, superior, etc.
        if device_type:
            return "camera"

        device_name = device.get("device_name", "no_name")
        self.logger.warning(f"Blink device with no device_type: '{device_name}'")
        return None

    async def build_switch(self: Blink2Mqtt, sync_module: dict[str, str]) -> str:
        device_id = sync_module["serial_number"]

        device = {
            "stat_t": self.mqtt_helper.stat_t(device_id, "state"),
            "cmd_t": self.mqtt_helper.cmd_t(device_id, "switch", "armed"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "device": {
                "name": sync_module["device_name"],
                "identifiers": [
                    self.mqtt_helper.device_slug(device_id),
                ],
                "manufacturer": sync_module["vendor"],
                "model": sync_module["device_type"],
                "serial_number": sync_module["serial_number"],
                "sw_version": sync_module["software_version"],
                "via_device": self.service,
            },
            "origin": {"name": self.service_name, "sw": self.config["version"], "support_url": "https://github.com/weirdTangent/blink2mqtt"},
            "qos": self.qos,
            "cmps": {
                "armed": {
                    "platform": "switch",
                    "name": "Armed",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "armed"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "switch", "armed"),
                    "cmd_t": self.mqtt_helper.cmd_t(device_id, "switch", "armed"),
                    "icon": "mdi:alarm-light",
                },
                "local_storage": {
                    "platform": "sensor",
                    "name": "Local storage",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "local_storage"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "switch", "local_storage"),
                    "icon": "mdi:usb-flash-drive",
                },
            },
        }

        self.upsert_device(device_id, component=device)
        await self.build_sync_module_states(device_id, sync_module)

        if not self.is_discovered(device_id):
            self.logger.info(f'added sync module: "{sync_module["device_name"]}" [Blink {sync_module["device_type"]}] (\'{self.get_device_name(device_id)}\')')

        await self.publish_device_discovery(device_id)
        await self.publish_device_availability(device_id, online=True)
        await self.publish_device_state(device_id)

        return device_id

    async def build_camera(self: Blink2Mqtt, camera: dict[str, str]) -> str:
        device_id = camera["serial_number"]
        via_device = self.resolve_camera_via_device(camera)

        device = {
            "stat_t": self.mqtt_helper.stat_t(device_id),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "device": {
                "name": camera["device_name"],
                "identifiers": [
                    self.mqtt_helper.device_slug(device_id),
                ],
                "manufacturer": camera["vendor"],
                "model": camera["device_type"],
                "serial_number": camera["serial_number"],
                "sw_version": camera["software_version"],
                "via_device": via_device or self.service,
            },
            "origin": {"name": self.service_name, "sw": self.config["version"], "support_url": "https://github.com/weirdTangent/blink2mqtt"},
            "qos": self.qos,
            "cmps": {
                "snapshot": {
                    "platform": "camera",
                    "name": "Snapshot",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "snapshot"),
                    "topic": self.mqtt_helper.stat_t(device_id, "snapshot"),
                    "image_encoding": "b64",
                    "icon": "mdi:camera",
                },
                "eventshot": {
                    "platform": "camera",
                    "name": "Event Snapshot",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "eventshot"),
                    "topic": self.mqtt_helper.stat_t(device_id, "eventshot"),
                    "image_encoding": "b64",
                    "icon": "mdi:camera",
                },
                "motion": {
                    "platform": "binary_sensor",
                    "name": "Motion",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "motion"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "binary_sensor", "motion"),
                    "pl_on": True,
                    "pl_off": False,
                    "icon": "mdi:motion-sensor-alert",
                },
                "motion_detection": {
                    "platform": "switch",
                    "name": "Motion Detection",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "motion_detection"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "switch", "motion_detection"),
                    "cmd_t": self.mqtt_helper.cmd_t(device_id, "switch", "motion_detection"),
                    "pl_on": "ON",
                    "pl_off": "OFF",
                    "icon": "mdi:motion-sensor",
                },
                "nightvision": {
                    "platform": "select",
                    "name": "Night Vision",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "nightvision"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "select", "nightvision"),
                    "cmd_t": self.mqtt_helper.cmd_t(device_id, "select", "nightvision"),
                    "options": ["auto", "on", "off"],
                    "icon": "mdi:light-flood-down",
                    "enabled_by_default": camera["supports_get_config"],
                },
                "temperature": {
                    "platform": "sensor",
                    "name": "Temperature",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "temperature"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "temperature"),
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "unit_of_measurement": "°F",
                    "icon": "mdi:thermometer",
                    "entity_category": "diagnostic",
                },
                "battery_status": {
                    "platform": "sensor",
                    "name": "Battery Status",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "battery_status"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "battery_status"),
                    "entity_category": "diagnostic",
                    "icon": "mdi:battery-alert",
                },
                "wifi_signal": {
                    "platform": "sensor",
                    "name": "Wifi Signal",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "wifi_signal"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "wifi_signal"),
                    "device_class": "signal_strength",
                    "unit_of_measurement": "dBm",
                    "icon": "mdi:wifi",
                    "entity_category": "diagnostic",
                },
                "last_event": {
                    "platform": "sensor",
                    "name": "Last Event",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "last_event"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "last_event"),
                    "icon": "mdi:message-text-outline",
                },
                "last_event_time": {
                    "platform": "sensor",
                    "name": "Last Event Time",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "last_event_time"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "last_event_time"),
                    "device_class": "timestamp",
                    "icon": "mdi:clock-outline",
                },
            },
        }

        self.upsert_device(device_id, component=device)
        await self.build_camera_states(device_id, camera)

        if not self.is_discovered(device_id):
            self.logger.info(f'added camera: "{camera["device_name"]}" [Blink {camera["device_type"]}] (\'{self.get_device_name(device_id)}\')')
            await self.publish_device_discovery(device_id)

        await self.publish_device_availability(device_id, online=True)
        await self.publish_device_state(device_id)

        return device_id

    def resolve_camera_via_device(self: Blink2Mqtt, camera: dict[str, Any]) -> str | None:
        """Return the MQTT device slug for the sync module a camera reports."""

        def normalize(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, bool):
                return str(int(value))
            if isinstance(value, (int, float)):
                return str(int(value))
            value = str(value).strip()
            return value or None

        sync_ref = camera.get("sync_module")
        if not sync_ref:
            return None

        candidate_values: set[str] = set()

        def add_candidate(value: Any) -> None:
            normalized = normalize(value)
            if normalized:
                candidate_values.add(normalized)

        if isinstance(sync_ref, dict):
            for key in ("serial", "serial_number", "device_id", "id", "network_id", "name"):
                add_candidate(sync_ref.get(key))
        elif isinstance(sync_ref, (list, tuple, set)):
            for item in sync_ref:
                add_candidate(item)
        else:
            for attr in ("serial", "serial_number", "device_id", "id", "network_id", "name"):
                add_candidate(getattr(sync_ref, attr, None))
            add_candidate(sync_ref)

        if not candidate_values:
            return None

        for device_id, device in self.blink_sync_modules.items():
            sync_candidates = {
                normalize(device_id),
                normalize(device.get("serial_number")),
                normalize(device.get("device_name")),
                normalize(device.get("sync_id")),
                normalize(device.get("network_id")),
            }
            if candidate_values & {value for value in sync_candidates if value}:
                slug = cast(str, self.mqtt_helper.device_slug(device_id))
                return slug

        return None
