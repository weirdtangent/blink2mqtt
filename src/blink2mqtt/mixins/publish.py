# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class PublishMixin:

    # Service -------------------------------------------------------------------------------------

    async def publish_service_discovery(self: Blink2Mqtt) -> None:
        device_id = "service"

        device = {
            "platform": "mqtt",
            "stat_t": self.mqtt_helper.stat_t(device_id, "state"),
            "cmd_t": self.mqtt_helper.cmd_t(device_id),
            "avty_t": self.mqtt_helper.avty_t(device_id),
            "device": {
                "name": self.service_name,
                "identifiers": [self.mqtt_helper.service_slug],
                "manufacturer": "weirdTangent",
                "sw_version": self.config["version"],
            },
            "origin": {"name": self.service_name, "sw": self.config["version"], "support_url": "https://github.com/weirdTangent/blink2mqtt"},
            "qos": self.qos,
            "cmps": {
                "server": {
                    "platform": "binary_sensor",
                    "name": self.service_name,
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "server"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "service", "server"),
                    "cmd_t": self.mqtt_helper.cmd_t(device_id),
                    "payload_on": "online",
                    "payload_off": "offline",
                    "device_class": "connectivity",
                    "entity_category": "diagnostic",
                    "icon": "mdi:server",
                },
                "api_calls": {
                    "platform": "sensor",
                    "name": "API calls today",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "api_calls"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "service", "api_calls"),
                    "unit_of_measurement": "calls",
                    "state_class": "total_increasing",
                    "entity_category": "diagnostic",
                    "icon": "mdi:api",
                },
                "rate_limited": {
                    "platform": "binary_sensor",
                    "name": "Rate limited",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "rate_limited"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "service", "rate_limited"),
                    "payload_on": "YES",
                    "payload_off": "NO",
                    "device_class": "problem",
                    "entity_category": "diagnostic",
                    "icon": "mdi:speedometer-slow",
                },
                "update_interval": {
                    "platform": "number",
                    "name": "Update interval",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "update_interval"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "service", "update_interval"),
                    "unit_of_measurement": "s",
                    "min": 1,
                    "max": 900,
                    "step": 1,
                    "mode": "box",
                    "icon": "mdi:timer-refresh",
                },
                "rescan_interval": {
                    "platform": "number",
                    "name": "Rescan interval",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "rescan_interval"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "service", "rescan_interval"),
                    "unit_of_measurement": "s",
                    "min": 1,
                    "max": 3600,
                    "step": 1,
                    "mode": "box",
                    "icon": "mdi:format-list_bulleted",
                },
                "snapshot_interval": {
                    "platform": "number",
                    "name": "Snapshot interval",
                    "uniq_id": self.mqtt_helper.dev_unique_id(device_id, "snapshot_interval"),
                    "stat_t": self.mqtt_helper.stat_t(device_id, "service", "snapshot_interval"),
                    "unit_of_measurement": "m",
                    "min": 1,
                    "max": 60,
                    "step": 1,
                    "mode": "box",
                    "icon": "mdi:lightning-bolt",
                },
            },
        }

        topic = self.mqtt_helper.disc_t("device", device_id)
        payload = {k: v for k, v in device.items() if k != "platform"}
        await asyncio.to_thread(self.mqtt_helper.safe_publish, topic, json.dumps(payload), retain=True)
        self.upsert_state(device_id, internal={"discovered": True})

        self.logger.debug(f"discovery published for {self.service} ({self.mqtt_helper.service_slug})")

    async def publish_service_availability(self: Blink2Mqtt, status: str = "online") -> None:
        await asyncio.to_thread(self.mqtt_helper.safe_publish, self.mqtt_helper.avty_t("service"), status, qos=self.qos, retain=True)

    async def publish_service_state(self: Blink2Mqtt) -> None:
        service = {
            "server": "online",
            "api_calls": self.get_api_calls(),
            "last_api_call": self.get_last_call_date(),
            "update_interval": self.device_interval,
            "rescan_interval": self.device_list_interval,
            "snapshot_interval": self.snapshot_update_interval,
            "rate_limited": "YES" if self.is_rate_limited() else "NO",
        }

        for key, value in service.items():
            await asyncio.to_thread(
                self.mqtt_helper.safe_publish,
                self.mqtt_helper.stat_t("service", "service", key),
                json.dumps(value) if isinstance(value, dict) else str(value),
                qos=self.mqtt_config["qos"],
                retain=True,
            )

    # Devices -------------------------------------------------------------------------------------

    async def publish_device_discovery(self: Blink2Mqtt, device_id: str) -> None:
        component = self.get_component(device_id)
        for slug, mode in self.get_modes(device_id).items():
            component["cmps"][f"{device_id}_{slug}"] = mode

        topic = self.mqtt_helper.disc_t("device", device_id)
        payload = {k: v for k, v in component.items() if k != "platform"}
        await asyncio.to_thread(self.mqtt_helper.safe_publish, topic, json.dumps(payload), retain=True)
        self.upsert_state(device_id, internal={"discovered": True})

    async def publish_device_availability(self: Blink2Mqtt, device_id: str, online: bool = True) -> None:
        payload = "online" if online else "offline"

        avty_t = self.get_device_availability_topic(device_id)
        await asyncio.to_thread(self.mqtt_helper.safe_publish, avty_t, payload, retain=True)

    async def publish_device_state(self: Blink2Mqtt, device_id: str, subject: str = "", sub: str = "") -> None:
        if not self.is_discovered(device_id):
            self.logger.debug(f"discovery not complete for {device_id} yet, holding off on sending state")
            return

        for state, value in self.states[device_id].items():
            if subject and state != subject:
                continue
            if isinstance(value, dict):
                for k, v in value.items():
                    if sub and k != sub:
                        continue
                    topic = self.mqtt_helper.stat_t(device_id, state, k)
                    await asyncio.to_thread(self.mqtt_helper.safe_publish, topic, v, retain=True)
            else:
                topic = self.mqtt_helper.stat_t(device_id, state)
                await asyncio.to_thread(self.mqtt_helper.safe_publish, topic, value, retain=True)

    async def publish_device_image(self: Blink2Mqtt, device_id: str, type: str) -> None:
        payload = self.states[device_id][type]
        if payload and isinstance(payload, str):
            self.logger.info(f"Updating {self.get_device_name(device_id)} with latest snapshot")
            topic = self.mqtt_helper.stat_t(device_id, type)
            await asyncio.to_thread(self.mqtt_helper.safe_publish, topic, payload, retain=True)
