# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse

from datetime import datetime
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.core import Blink2Mqtt
    from blink2mqtt.interface import BlinkServiceProtocol


class ServiceMixin:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    def publish_service_discovery(self: Blink2Mqtt) -> None:
        app = self.get_device_block(self.service_slug, self.service_name)

        self.mqtt_safe_publish(
            topic=self.get_discovery_topic("binary_sensor", self.service_slug),
            payload=json.dumps(
                {
                    "name": self.service_name,
                    "uniq_id": self.service_slug,
                    "stat_t": self.get_service_topic("status"),
                    "payload_on": "online",
                    "payload_off": "offline",
                    "device_class": "connectivity",
                    "icon": "mdi:server",
                    "device": app,
                    "origin": {
                        "name": self.service_name,
                        "sw_version": self.config["version"],
                        "support_url": "https://github.com/weirdtangent/blink2mqtt",
                    },
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )

        self.mqtt_safe_publish(
            topic=self.get_discovery_topic("sensor", f"{self.service_slug}_api_calls"),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} API Calls Today",
                    "uniq_id": f"{self.service_slug}_api_calls",
                    "stat_t": self.get_state_topic("service", "service", "api_calls"),
                    "json_attr_t": self.get_attribute_topic(
                        "service", "service", "api_calls", "attributes"
                    ),
                    "unit_of_measurement": "calls",
                    "icon": "mdi:api",
                    "state_class": "total_increasing",
                    "device": app,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_safe_publish(
            topic=self.get_discovery_topic(
                "binary_sensor", f"{self.service_slug}_rate_limited"
            ),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Rate Limited by Blink",
                    "uniq_id": f"{self.service_slug}_rate_limited",
                    "stat_t": self.get_state_topic(
                        "service", "service", "rate_limited"
                    ),
                    "json_attr_t": self.get_attribute_topic(
                        "service", "service", "rate_limited", "attributes"
                    ),
                    "payload_on": "yes",
                    "payload_off": "no",
                    "device_class": "problem",
                    "icon": "mdi:speedometer-slow",
                    "device": app,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_safe_publish(
            topic=self.get_discovery_topic(
                "number", f"{self.service_slug}_device_refresh"
            ),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Device Refresh Interval",
                    "uniq_id": f"{self.service_slug}_device_refresh",
                    "stat_t": self.get_state_topic(
                        "service", "service", "device_refresh"
                    ),
                    "json_attr_t": self.get_attribute_topic(
                        "service", "service", "device_refresh", "attributes"
                    ),
                    "cmd_t": self.get_command_topic("service", "device_refresh"),
                    "unit_of_measurement": "s",
                    "min": 1,
                    "max": 3600,
                    "step": 1,
                    "icon": "mdi:timer-refresh",
                    "device": app,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_safe_publish(
            topic=self.get_discovery_topic(
                "number", f"{self.service_slug}_device_list_refresh"
            ),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Device List Refresh Interval",
                    "uniq_id": f"{self.service_slug}_device_list_refresh",
                    "stat_t": self.get_state_topic(
                        "service", "service", "device_list_refresh"
                    ),
                    "json_attr_t": self.get_attribute_topic(
                        "service", "service", "device_list_refresh", "attributes"
                    ),
                    "cmd_t": self.get_command_topic("service", "device_list_refresh"),
                    "unit_of_measurement": "s",
                    "min": 1,
                    "max": 3600,
                    "step": 1,
                    "icon": "mdi:format-list-bulleted",
                    "device": app,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_safe_publish(
            topic=self.get_discovery_topic(
                "number", f"{self.service_slug}_snapshot_refresh"
            ),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Device Boost Refresh Interval",
                    "uniq_id": f"{self.service_slug}_snapshot_refresh",
                    "stat_t": self.get_state_topic(
                        "service", "service", "snapshot_refresh"
                    ),
                    "json_attr_t": self.get_attribute_topic(
                        "service", "service", "snapshot_refresh", "attributes"
                    ),
                    "cmd_t": self.get_command_topic("service", "snapshot_refresh"),
                    "unit_of_measurement": "s",
                    "min": 1,
                    "max": 30,
                    "step": 1,
                    "icon": "mdi:lightning-bolt",
                    "device": app,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_safe_publish(
            topic=self.get_discovery_topic(
                "button", f"{self.service_slug}_refresh_device_list"
            ),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Refresh Device List",
                    "uniq_id": f"{self.service_slug}_refresh_device_list",
                    "cmd_t": self.get_command_topic(
                        "service", "refresh_device_list", "command"
                    ),
                    "payload_press": "refresh",
                    "icon": "mdi:refresh",
                    "device": app,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.logger.debug(
            f"[HA] Discovery published for {self.service} ({self.service_slug})"
        )

    def publish_service_availability(self: Blink2Mqtt, status: str = "online") -> None:
        self.mqtt_safe_publish(
            self.get_service_topic("status"), status, qos=self.qos, retain=True
        )

    def publish_service_state(self: Blink2Mqtt) -> None:
        service = {
            "state": "online",
            "api_calls": {
                "api_calls": self.get_api_calls(),
                "last_api_call": self.get_last_call_date(),
            },
            "rate_limited": "yes" if self.is_rate_limited() else "no",
            "device_refresh": self.device_interval,
            "device_list_refresh": self.device_list_interval,
            "snapshot_refresh": self.snapshot_update_interval,
        }

        for key, value in service.items():
            # Scalars like "state" -> just publish as is (but as a string)
            if not isinstance(value, dict):
                payload = str(value)
            else:
                payload = value.get(key)
                if isinstance(payload, datetime):
                    payload = payload.isoformat()
                payload = json.dumps(payload)

            self.mqtt_safe_publish(
                self.get_state_topic("service", "service", key),
                payload,
                qos=self.mqtt_config["qos"],
                retain=True,
            )
