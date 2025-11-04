# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class BlinkMixin:
    async def refresh_device_list(self: Blink2Mqtt) -> None:
        if self.discovery_complete:
            self.logger.info(f"Refreshing device list from Blink (every {self.device_list_interval} sec)")
        else:
            self.logger.info("Grabbing device list from Blink")

        blink_devices = await self.get_cameras()
        sync_modules = await self.get_sync_modules()

        self.publish_service_state()

        seen_devices = set()

        for device in sync_modules.values():
            created = self.build_component(device["config"])
            seen_devices.add(created)

        for device in blink_devices.values():
            created = self.build_component(device["config"])
            seen_devices.add(created)

        # Mark missing devices offline
        missing_devices = set(self.devices.keys()) - seen_devices
        for device_id in missing_devices:
            self.publish_device_availability(device_id, online=False)
            self.logger.warning(f"Device {device_id} not seen in Blink API list — marked offline")

        # Handle first discovery completion
        if not self.discovery_complete:
            await asyncio.sleep(1)
            self.logger.info("First-time device setup and discovery is done")
            self.discovery_complete = True

    # convert Blink device capabilities into MQTT components
    def build_component(self: Blink2Mqtt, device: dict[str, str]) -> str:
        device_class = self.classify_device(device)
        match device_class:
            case "switch":
                return self.build_switch(device)
            case "camera":
                return self.build_camera(device)
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

        self.logger.debug(f'Unrecognized Blink device type: "{device_name}" [{type}] ({device_id})')

        return None

    def build_switch(self: Blink2Mqtt, sync_module: dict[str, str]) -> str:
        device_id = sync_module["serial_number"]

        modes = {}

        component = {
            "component_type": "switch",
            "name": f"{sync_module["device_name"]} Armed",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "armed"),
            "stat_t": self.mqtt_helper.stat_t(device_id, "switch", "armed"),
            "cmd_t": self.mqtt_helper.cmd_t(device_id, "switch", "armed"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "icon": "mdi:alarm-light",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                sync_module["device_name"],
                self.mqtt_helper.device_slug(device_id),
                sync_module["vendor"],
                sync_module["software_version"],
            ),
        }

        modes["local_storage"] = {
            "component_type": "sensor",
            "name": "Local storage",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "local_storage"),
            "stat_t": self.mqtt_helper.stat_t(device_id, "switch", "local_storage"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "icon": "mdi:usb-flash-drive",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                sync_module["device_name"],
                self.mqtt_helper.device_slug(device_id),
                sync_module["vendor"],
                sync_module["software_version"],
            ),
        }

        self.upsert_state(device_id, internal={"raw_id": device_id})
        self.upsert_device(device_id, component=component, modes=modes)
        self.build_sync_module_states(device_id, sync_module)

        if not self.is_discovered(device_id):
            self.logger.info(f'Added new switch: "{sync_module["device_name"]}" [Blink {sync_module["device_type"]}] ({device_id})')

        self.publish_device_discovery(device_id)
        self.publish_device_availability(device_id, online=True)
        self.publish_device_state(device_id)

        return device_id

    def build_camera(self: Blink2Mqtt, camera: dict[str, str]) -> str:
        raw_id = camera["serial_number"]
        device_id = raw_id

        component = {
            "component_type": "camera",
            "name": "Snapshot",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "snapshot"),
            "topic": self.mqtt_helper.stat_t(device_id, "snapshot"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "image_encoding": "b64",
            "icon": "mdi:camera",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                camera["device_name"],
                self.mqtt_helper.device_slug(device_id),
                camera["software_version"],
                camera["vendor"],
            ),
        }
        self.upsert_state(device_id, internal={"raw_id": raw_id}, camera="online", snapshot=None)
        modes = {}

        modes["eventshot"] = {
            "component_type": "camera",
            "name": "Event Snapshot",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "eventshot"),
            "topic": self.mqtt_helper.stat_t(device_id, "eventshot"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "image_encoding": "b64",
            "icon": "mdi:camera",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                camera["device_name"],
                self.mqtt_helper.device_slug(device_id),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["motion"] = {
            "component_type": "binary_sensor",
            "name": "Motion",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "motion"),
            "stat_t": self.mqtt_helper.stat_t(device_id, "binary_sensor", "motion"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "pl_on": True,
            "pl_off": False,
            "icon": "mdi:motion-sensor-alert",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                camera["device_name"],
                self.mqtt_helper.device_slug(device_id),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["motion_detection"] = {
            "component_type": "switch",
            "name": "Motion Detection",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "motion_detection"),
            "stat_t": self.mqtt_helper.stat_t(device_id, "switch", "motion_detection"),
            "cmd_t": self.mqtt_helper.cmd_t(device_id, "switch", "motion_detection"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "pl_on": "ON",
            "pl_off": "OFF",
            "icon": "mdi:motion-sensor",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                camera["device_name"],
                self.mqtt_helper.device_slug(device_id),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["temperature"] = {
            "component_type": "sensor",
            "name": "Temperature",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "temperature"),
            "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "temperature"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "device_class": "temperature",
            "state_class": "measurement",
            "unit_of_measurement": "°F",
            "icon": "mdi:thermometer",
            "entity_category": "diagnostic",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                camera["device_name"],
                self.mqtt_helper.device_slug(device_id),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["battery_status"] = {
            "component_type": "sensor",
            "name": "Battery Status",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "battery_status"),
            "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "battery_status"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "entity_category": "diagnostic",
            "icon": "mdi:battery-alert",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                camera["device_name"],
                self.mqtt_helper.device_slug(device_id),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["wifi_signal"] = {
            "component_type": "sensor",
            "name": "Wifi Signal",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "wifi_signal"),
            "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "wifi_signal"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "device_class": "signal_strength",
            "unit_of_measurement": "dBm",
            "icon": "mdi:wifi",
            "entity_category": "diagnostic",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                camera["device_name"],
                self.mqtt_helper.device_slug(device_id),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["last_event"] = {
            "component_type": "sensor",
            "name": "Last Event",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "last_event"),
            "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "last_event"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "icon": "mdi:message-text-outline",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                camera["device_name"],
                self.mqtt_helper.device_slug(device_id),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["last_event_time"] = {
            "component_type": "sensor",
            "name": "Last Event Time",
            "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "last_event_time"),
            "stat_t": self.mqtt_helper.stat_t(device_id, "sensor", "last_event_time"),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "device_class": "timestamp",
            "icon": "mdi:clock-outline",
            "via_device": self.mqtt_helper.service_slug,
            "device": self.mqtt_helper.device_block(
                camera["device_name"],
                self.mqtt_helper.device_slug(device_id),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        # [INFO] blink_mqtt.mixins.base: Checking blink_device: {"name": "Great Room", "device_name": "Great Room", "device_type": "catalina",
        #                                                        "serial_number": "G8T1GH0121330NSG", "software_version": "10.71", "vendor": "Amazon",
        #                                                        "sync_module": "2nd Floor", "arm_mode": false, "motion": false, "temperature": 73,
        #                                                        "battery": "ok", "battery_voltage": 169, "wifi_strength": -46, "sync_strength": null}

        self.upsert_device(device_id, component=component, modes=modes)
        self.build_camera_states(device_id, camera)

        if not self.is_discovered(device_id):
            self.logger.info(f'Added new camera: "{camera["device_name"]}" [Blink {camera["device_type"]}] ({device_id})')

        self.publish_device_discovery(device_id)
        self.publish_device_availability(device_id, online=True)
        self.publish_device_state(device_id)

        return device_id
