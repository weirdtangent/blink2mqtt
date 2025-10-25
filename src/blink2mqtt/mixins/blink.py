# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.core import Blink2Mqtt
    from blink2mqtt.interface import BlinkServiceProtocol


class BlinkMixin:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    async def refresh_device_list(self: Blink2Mqtt) -> None:
        self.logger.info(
            f"Refreshing device list from Blink (every {self.device_list_interval} sec)"
        )

        blink_devices = await self.get_cameras()
        sync_modules = await self.get_sync_modules()

        self.publish_service_state()

        seen_devices = set()

        for device_id in sync_modules:
            sync_module = sync_modules[device_id]["config"]
            self.logger.info(f"Checking sync_module: {sync_module["device_name"]}")

            created = self.build_component(sync_module)
            seen_devices.update(created)

        for device_id in blink_devices:
            camera = blink_devices[device_id]["config"]
            self.logger.info(f"Checking blink_device: {camera["device_name"]}")

            created = self.build_component(camera)
            seen_devices.update(created)

        # Mark missing devices offline
        # missing_devices = set(self.devices.keys()) - seen_devices
        # for device_id in missing_devices:
        #     self.publish_device_availability(device_id, online=False)
        #     self.logger.warning(
        #         f"Device {device_id} not seen in Blink API list — marked offline"
        #     )

        # Handle first discovery completion
        if not self.discovery_complete:
            await asyncio.sleep(1)
            self.logger.info("First-time device setup and discovery is done")
            self.discovery_complete = True

    # convert Blink device capabilities into MQTT components
    def build_component(self: Blink2Mqtt, device: list) -> []:
        device_class = self.classify_device(device)
        match device_class:
            case "switch":
                return self.build_switch(device)
            case "camera":
                return self.build_camera(device)
        return []

    def classify_device(self: Blink2Mqtt, device: list) -> str | None:
        type = device.get("device_type", None)

        if type == "sync_module":
            return "switch"
        if type == "sedona" or type == "catalina":
            return "camera"

        # If we reach here, it's unsupported — log details for future handling
        device_name = device.get("device_name", "Unknown Device")
        device_id = device.get("serial_number", "Unknown ID")

        self.logger.debug(
            f'Unrecognized Blink device type: "{device_name}" [{type}] ({device_id})'
        )

        return None

    def build_switch(self: Blink2Mqtt, sync_module: list[str, str]) -> str:
        raw_id = sync_module["serial_number"]
        device_id = raw_id

        self.devices.setdefault(device_id, {})

        component = {
            "component_type": "switch",
            "name": f"{sync_module["device_name"]} Armed",
            "uniq_id": f"{self.service_slug}_{self.get_device_slug(device_id, 'armed')}",
            "stat_t": self.get_state_topic(device_id, "switch", "armed"),
            "cmd_t": self.get_command_topic(device_id, "switch", "armed"),
            "avty_t": self.get_availability_topic(device_id),
            "pl_avail": "online",
            "pl_not_avail": "offline",
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:alarm-light",
            "via_device": self.get_service_device(),
            "device": self.get_device_block(
                self.get_device_slug(device_id),
                sync_module["device_name"],
                self.get_service_device(),
                sync_module["software_version"],
                sync_module["vendor"],
            ),
        }
        self.upsert_state(device_id, internal={"raw_id": raw_id})
        modes = {}

        # add local storage ?
        modes["local_storage"] = {
            "component_type": "sensor",
            "name": "Local storage",
            "uniq_id": f"{self.service_slug}_{self.get_device_slug(device_id, 'local_storage')}",
            "stat_t": self.get_state_topic(device_id, "sensor", "local_storage"),
            "avty_t": self.get_availability_topic(device_id),
            "pl_avail": "online",
            "pl_not_avail": "offline",
            "payload_on": "on",
            "payload_off": "off",
            "icon": "mdi:usb-flash-drive",
            "via_device": self.get_service_device(),
            "device": self.get_device_block(
                self.get_device_slug(device_id),
                sync_module["device_name"],
                self.get_service_device(),
                sync_module["software_version"],
                sync_module["vendor"],
            ),
        }

        # insert, or update anything that changed, but don't lose anything
        self.upsert_device(device_id, component=component, modes=modes)
        self.build_sync_module_states(device_id, sync_module)

        if not self.is_discovered(device_id):
            self.logger.info(
                f'Added new switch: "{sync_module["device_name"]}" [Blink {sync_module["device_type"]}] ({device_id})'
            )

        self.publish_device_discovery(device_id)
        self.publish_device_availability(device_id, online=True)
        self.publish_device_state(device_id)

        return device_id

    def build_camera(self: Blink2Mqtt, camera: list[str, str]) -> str:
        raw_id = camera["serial_number"]
        device_id = raw_id

        component = {
            "component_type": "camera",
            "name": "Snapshot",
            "uniq_id": f"{self.service_slug}_{self.get_device_slug(device_id, 'snapshot')}",
            "topic": self.get_state_topic(device_id, "snapshot"),
            "image_encoding": "b64",
            "avty_t": self.get_availability_topic(device_id, "camera"),
            "avty_tpl": "{{ value_json.availability }}",
            "json_attributes_topic": self.get_state_topic(device_id, "attributes"),
            "pl_avail": "online",
            "pl_not_avail": "offline",
            "icon": "mdi:camera",
            "via_device": self.get_service_device(),
            "device": self.get_device_block(
                self.get_device_slug(device_id),
                camera["device_name"],
                self.get_service_device(),
                camera["software_version"],
                camera["vendor"],
            ),
        }
        self.upsert_state(device_id, internal={"raw_id": raw_id}, camera="online", snapshot=None)
        modes = {}

        modes["event"] = {
            "component_type": "camera",
            "name": "Event",
            "uniq_id": f"{self.service_slug}_{self.get_device_slug(device_id, 'event')}",
            "topic": self.get_state_topic(device_id, "event"),
            "image_encoding": "b64",
            "avty_t": self.get_availability_topic(device_id, "camera"),
            "avty_tpl": "{{ value_json.availability }}",
            "json_attributes_topic": self.get_state_topic(device_id, "attributes"),
            "pl_avail": "online",
            "pl_not_avail": "offline",
            "icon": "mdi:camera",
            "via_device": self.get_service_device(),
            "device": self.get_device_block(
                self.get_device_slug(device_id),
                camera["device_name"],
                self.get_service_device(),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["motion"] = {
            "component_type": "binary_sensor",
            "name": "Motion",
            "uniq_id": f"{self.service_slug}_{self.get_device_slug(device_id, 'motion')}",
            "stat_t": self.get_state_topic(device_id, "camera", "attributes"),
            "value_template": "{{ value_json.motion }}",
            "json_attributes_topic": self.get_state_topic(device_id, "attributes"),
            "avty_t": self.get_availability_topic(device_id, "camera"),
            "avty_tpl": "{{ value_json.availability }}",
            "pl_on": True,
            "pl_off": False,
            "icon": "mdi:motion-sensor-alert",
            "via_device": self.get_service_device(),
            "device": self.get_device_block(
                self.get_device_slug(device_id),
                camera["device_name"],
                self.get_service_device(),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["motion_detection"] = {
            "component_type": "switch",
            "name": "Motion Detection",
            "uniq_id": f"{self.service_slug}_{self.get_device_slug(device_id, 'motion_detection')}",
            "stat_t": self.get_state_topic(device_id, "switch", "motion_detection"),
            "cmd_t": self.get_command_topic(device_id, "switch", "motion_detection"),
            "avty_t": self.get_availability_topic(device_id, "camera"),
            "avty_tpl": "{{ value_json.availability }}",
            "pl_on": "ON",
            "pl_off": "OFF",
            "icon": "mdi:motion-sensor",
            "via_device": self.get_service_device(),
            "device": self.get_device_block(
                self.get_device_slug(device_id),
                camera["device_name"],
                self.get_service_device(),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["temperature"] = {
            "component_type": "sensor",
            "name": "Temperature",
            "uniq_id": f"{self.service_slug}_{self.get_device_slug(device_id, 'temperature')}",
            "stat_t": self.get_state_topic(device_id, "sensor", "temperature"),
            "avty_t": self.get_availability_topic(device_id, "camera"),
            "avty_tpl": "{{ value_json.availability }}",
            "device_class": "temperature",
            "state_class": "measurement",
            "unit_of_measurement": "°F",
            "icon": "mdi:thermometer",
            "via_device": self.get_service_device(),
            "device": self.get_device_block(
                self.get_device_slug(device_id),
                camera["device_name"],
                self.get_service_device(),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["battery_status"] = {
            "component_type": "sensor",
            "name": "Battery Status",
            "uniq_id": f"{self.service_slug}_{self.get_device_slug(device_id, 'battery_status')}",
            "stat_t": self.get_state_topic(device_id, "sensor", "battery_status"),
            "avty_t": self.get_availability_topic(device_id, "camera"),
            "avty_tpl": "{{ value_json.availability }}",
            "entity_category": "diagnostic",
            "icon": "mdi:battery-alert",
            "via_device": self.get_service_device(),
            "device": self.get_device_block(
                self.get_device_slug(device_id),
                camera["device_name"],
                self.get_service_device(),
                camera["software_version"],
                camera["vendor"],
            ),
        }

        modes["wifi_signal"] = {
            "component_type": "sensor",
            "name": "Wifi Signal",
            "uniq_id": f"{self.service_slug}_{self.get_device_slug(device_id, 'wifi_signal')}",
            "stat_t": self.get_state_topic(device_id, "sensor", "wifi_signal"),
            "avty_t": self.get_availability_topic(device_id, "camera"),
            "avty_tpl": "{{ value_json.availability }}",
            "device_class": "signal_strength",
            "unit_of_measurement": "dBm",
            "icon": "mdi:wifi",
            "entity_category": "diagnostic",
            "via_device": self.get_service_device(),
            "device": self.get_device_block(
                self.get_device_slug(device_id),
                camera["device_name"],
                self.get_service_device(),
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
            self.logger.info(
                f'Added new camera: "{camera["device_name"]}" [Blink {camera["device_type"]}] ({device_id})'
            )

        self.publish_device_discovery(device_id)
        self.publish_device_availability(device_id, online=True)
        self.publish_device_state(device_id)

        return device_id

    def publish_device_discovery(self: Blink2Mqtt, device_id: str) -> None:
        def _publish_one(dev_id: str, defn: dict, suffix: str | None = None):
            # Compute a per-mode device_id for topic namespacing
            eff_device_id = dev_id if not suffix else f"{dev_id}_{suffix}"

            # Grab this component's discovery topic
            topic = self.get_discovery_topic(defn["component_type"], eff_device_id)

            # Shallow copy to avoid mutating source
            payload = {k: v for k, v in defn.items() if k != "component_type"}

            # Publish discovery
            self.mqtt_safe_publish(topic, json.dumps(payload), retain=True)

            # Mark discovered in state (per published entity)
            self.states.setdefault(eff_device_id, {}).setdefault("internal", {})[
                "discovered"
            ] = 1

        component = self.get_component(device_id)
        _publish_one(device_id, component, suffix=None)

        # Publish any modes (0..n)
        modes = self.get_modes(device_id)
        for slug, mode in modes.items():
            _publish_one(device_id, mode, suffix=slug)

    def publish_device_state(self: Blink2Mqtt, device_id: str) -> None:
        def _publish_one(dev_id: str, mode_name: str, defn):
            # Grab device states and this component's state topic
            topic = self.get_device_state_topic(dev_id, mode_name)

            # Shallow copy to avoid mutating source
            flat = None
            if isinstance(defn, dict):
                payload = {k: v for k, v in defn.items() if k != "component_type"}
                flat = None

                if not payload:
                    flat = ""
                elif not isinstance(payload, dict):
                    flat = payload
                else:
                    flat = {}
                    for k, v in payload.items():
                        if k == "component_type":
                            continue
                        flat[k] = v

                # Add metadata
                meta = states.get("meta")
                if isinstance(meta, dict) and "last_update" in meta:
                    flat["last_update"] = meta["last_update"]
                self.mqtt_safe_publish(topic, json.dumps(flat), retain=True)
            else:
                flat = defn
                self.mqtt_safe_publish(topic, flat, retain=True)

        if not self.is_discovered(device_id):
            self.logger.debug(
                f"[device state] Discovery not complete for {device_id} yet, holding off on sending state"
            )
            return

        states = self.states.get(device_id, None)
        _publish_one(device_id, "", states[self.get_component_type(device_id)])

        # Publish any modes (0..n)
        modes = self.get_modes(device_id)
        for name, mode in modes.items():
            component_type = mode["component_type"]
            type_states = (
                states[component_type][name]
                if isinstance(states[component_type], dict)
                else states[component_type]
            )
            _publish_one(device_id, name, type_states)

    def publish_device_image(self: Blink2Mqtt, device_id: str, type: str) -> None:
        payload = self.states[device_id][type]
        if payload and isinstance(payload, str):
            self.logger.info(
                f"Updating {self.get_device_name(device_id)} with latest snapshot"
            )
            topic = self.get_device_image_topic(device_id)
            self.mqtt_safe_publish(topic, payload, retain=True)

    def publish_device_availability(
        self: Blink2Mqtt, device_id: str, online: bool = True
    ) -> None:
        payload = "online" if online else "offline"

        # if state and availability are the SAME, we don't want to
        # overwrite the big json state with just online/offline
        stat_t = self.get_device_state_topic(device_id)
        avty_t = self.get_device_availability_topic(device_id)
        if stat_t and avty_t and stat_t == avty_t:
            return

        self.mqtt_safe_publish(avty_t, payload, retain=True)

