# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from __future__ import annotations

import concurrent.futures
from typing import TYPE_CHECKING, Any

from mqtt_helper import BaseMqttMixin, decode_mqtt_payload, parse_device_topic
from paho.mqtt.client import Client, MQTTMessage

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class MqttMixin(BaseMqttMixin):
    # Bump ONLY when the entity layout changes: unique_ids, entity names, or the set of components
    # published. A bump clears retained discovery on next connect, which drops the entities from
    # HA's registry -- losing renames, areas, and hidden/disabled flags -- before recreating them.
    #
    # 1: baseline (2026-08) -- first version to carry a schema stamp, plus the reset_discovery button
    DISCOVERY_SCHEMA_VERSION = 1

    def mqtt_subscription_topics(self: Blink2Mqtt) -> list[str]:
        return [
            "homeassistant/status",
            f"{self.mqtt_helper.service_slug}/service/+/set",
            f"{self.mqtt_helper.service_slug}/service/+/command",
            f"{self.mqtt_helper.service_slug}/+/switch/+/set",
        ]

    async def mqtt_on_message(self: Blink2Mqtt, client: Client, userdata: Any, msg: MQTTMessage) -> None:
        topic = msg.topic
        components = topic.split("/")

        payload = decode_mqtt_payload(msg.payload)
        if payload is None:
            return None

        if components[0] == self.mqtt_config["discovery_prefix"] and payload:
            return await self.handle_homeassistant_message(payload)

        if components[0] == self.mqtt_helper.service_slug and components[1] == "service":
            return await self.handle_service_command(components[2], payload)

        if components[0] == self.mqtt_helper.service_slug:
            return await self.handle_device_topic(components, payload)

        self.logger.debug(f"ignoring unrelated MQTT topic: {topic}")

    async def handle_homeassistant_message(self: Blink2Mqtt, payload: str) -> None:
        if payload == "online":
            await self.rediscover_all()
            self.logger.info("home assistant came online — rediscovering devices")

    async def handle_device_topic(self: Blink2Mqtt, components: list[str], payload: Any) -> None:
        parsed = parse_device_topic(components)
        if not parsed:
            return

        vendor, device_id, attribute = parsed
        if not vendor or not vendor.startswith(self.mqtt_helper.service_slug):
            self.logger.error(f"ignoring non-Blink device command, got vendor {vendor}")
            return
        if not device_id or not attribute:
            self.logger.error(f"failed to parse device_id and/or payload from mqtt topic components: {components}")
            return
        if not self.devices.get(device_id, None):
            self.logger.warning(f"got MQTT message for unknown device: '{self.get_device_name(device_id)}'")
            return

        self.logger.info(f"got message for '{self.get_device_name(device_id)}': set {components[-2]} to {payload}")
        await self.handle_device_command(device_id, attribute, payload)

    def set_discovered(self: Blink2Mqtt, device_id: str) -> None:
        self.upsert_state(device_id, internal={"discovered": True})

    def log_future_result(self: Blink2Mqtt, fut: concurrent.futures.Future) -> None:
        try:
            fut.result()
        except Exception:
            self.logger.exception("device command task failed")
