# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class BlinkMixin:
    async def refresh_device_list(self: Blink2Mqtt) -> None:
        if self.discovery_complete:
            self.logger.info(f"Refreshing device list from Blink (every {self.device_list_interval} sec)")
        else:
            self.logger.info("Grabbing device list from Blink")

        blink_devices, sync_modules = await asyncio.gather(
            self.get_cameras(),
            self.get_sync_modules(),
        )

        await self.publish_service_state()

        seen_devices: set[str] = set()

        # Build both camera and sync devices in parallel (CPU-bound but cheap)
        async def build_and_track(device: dict[str, Any]) -> None:
            created = await self.build_component(device["config"])
            seen_devices.add(created)

        tasks = [
            *(build_and_track(d) for d in sync_modules.values()),
            *(build_and_track(d) for d in blink_devices.values()),
        ]
        if tasks:
            await asyncio.gather(*tasks)

        # Mark missing devices offline
        missing_devices = set(self.devices.keys()) - seen_devices
        for device_id in missing_devices:
            await self.publish_device_availability(device_id, online=False)
            self.logger.warning(f"Device {device_id} not seen in Blink API list — marked offline")

        # Handle first discovery completion
        if not self.discovery_complete:
            await asyncio.sleep(1)
            self.logger.info("First-time device setup and discovery is done")
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
        type = device.get("device_type", None)

        if type == "sync_module":
            return "switch"
        if type == "sedona" or type == "catalina":
            return "camera"

        # If we reach here, it's unsupported — log details for future handling
        device_name = device.get("device_name", "Unknown Device")
        device_id = device.get("serial_number", "Unknown ID")

        self.logger.warning(f'Unhandled Blink device type: "{device_name}" [{type}] ({device_id})')
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

        self.upsert_state(device_id, internal={"raw_id": device_id}, mqtt={}, state={})
        self.upsert_device(device_id, component=device, cmps={k: v for k, v in device["cmps"].items()})
        await self.build_sync_module_states(device_id, sync_module)

        if not self.is_discovered(device_id):
            self.logger.info(f'Added new switch: "{sync_module["device_name"]}" [Blink {sync_module["device_type"]}] ({device_id})')

        await self.publish_device_discovery(device_id)
        await self.publish_device_availability(device_id, online=True)
        await self.publish_device_state(device_id)

        return device_id

    async def build_camera(self: Blink2Mqtt, camera: dict[str, str]) -> str:
        device_id = camera["serial_number"]

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
                "via_device": self.service,
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
                "night_vision": {
                    "platform": "select",
                    "name": "Night Vision",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "night_vision"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "switch", "night_vision"),
                    "cmd_t": self.mqtt_helper.cmd_t(device_id, "switch", "night_vision"),
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

        self.upsert_device(device_id, component=device, cmps={k: v for k, v in device["cmps"].items()})
        self.upsert_state(device_id, internal={"raw_id": device_id})
        await self.build_camera_states(device_id, camera)

        if not self.is_discovered(device_id):
            self.logger.info(f'Added new camera: "{camera["device_name"]}" [Blink {camera["device_type"]}] ({device_id})')

        await self.publish_device_discovery(device_id)
        await self.publish_device_availability(device_id, online=True)
        await self.publish_device_state(device_id)

        return device_id
