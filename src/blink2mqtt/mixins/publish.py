# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class PublishMixin:

    # Service -------------------------------------------------------------------------------------

    def publish_service_discovery(self: Blink2Mqtt) -> None:
        device_block = self.mqtt_helper.device_block(
            self.service_name,
            self.mqtt_helper.service_slug,
            "weirdTangent",
            self.config["version"],
        )

        self.mqtt_helper.safe_publish(
            topic=self.mqtt_helper.disc_t("binary_sensor", "service"),
            payload=json.dumps(
                {
                    "name": self.service_name,
                    "uniq_id": self.mqtt_helper.svc_unique_id("service"),
                    "stat_t": self.mqtt_helper.avty_t("service"),
                    "avty_t": self.mqtt_helper.avty_t("service"),
                    "device_class": "connectivity",
                    "icon": "mdi:server",
                    "device": device_block,
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

        self.mqtt_helper.safe_publish(
            topic=self.mqtt_helper.disc_t("sensor", "api_calls"),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} API Calls Today",
                    "uniq_id": self.mqtt_helper.svc_unique_id("api_calls"),
                    "stat_t": self.mqtt_helper.stat_t("service", "service", "api_calls"),
                    "avty_t": self.mqtt_helper.avty_t("service"),
                    "unit_of_measurement": "calls",
                    "icon": "mdi:api",
                    "state_class": "total_increasing",
                    "device": device_block,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_helper.safe_publish(
            topic=self.mqtt_helper.disc_t("binary_sensor", "rate_limited"),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Rate Limited by Blink",
                    "uniq_id": self.mqtt_helper.svc_unique_id("rate_limited"),
                    "stat_t": self.mqtt_helper.stat_t("service", "service", "rate_limited"),
                    "avty_t": self.mqtt_helper.avty_t("service"),
                    "json_attr_t": self.mqtt_helper.attr_t("service"),
                    "payload_on": "YES",
                    "payload_off": "NO",
                    "device_class": "problem",
                    "icon": "mdi:speedometer-slow",
                    "device": device_block,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_helper.safe_publish(
            topic=self.mqtt_helper.disc_t("number", "device_update_interval"),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Device Update Interval",
                    "uniq_id": self.mqtt_helper.svc_unique_id("device_update_interval"),
                    "stat_t": self.mqtt_helper.stat_t("service", "service", "device_update_interval"),
                    "avty_t": self.mqtt_helper.avty_t("service"),
                    "json_attr_t": self.mqtt_helper.attr_t("service"),
                    "cmd_t": self.mqtt_helper.cmd_t("service", "device_update_interval"),
                    "unit_of_measurement": "s",
                    "min": 1,
                    "max": 900,
                    "step": 1,
                    "icon": "mdi:timer-refresh",
                    "device": device_block,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_helper.safe_publish(
            topic=self.mqtt_helper.disc_t("number", "device_rescan_interval"),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Device Rescan Interval",
                    "uniq_id": self.mqtt_helper.svc_unique_id("device_rescan_interval"),
                    "stat_t": self.mqtt_helper.stat_t("service", "service", "device_rescan_interval"),
                    "avty_t": self.mqtt_helper.avty_t("service"),
                    "json_attr_t": self.mqtt_helper.attr_t("service"),
                    "cmd_t": self.mqtt_helper.cmd_t("service", "device_rescan_interval"),
                    "unit_of_measurement": "s",
                    "min": 1,
                    "max": 3600,
                    "step": 1,
                    "icon": "mdi:format-list-bulleted",
                    "device": device_block,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_helper.safe_publish(
            topic=self.mqtt_helper.disc_t("number", "snapshot_update_interval"),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Snapshot Update Interval",
                    "uniq_id": self.mqtt_helper.svc_unique_id("snapshot_update_interval"),
                    "stat_t": self.mqtt_helper.stat_t("service", "service", "snapshot_update_interval"),
                    "avty_t": self.mqtt_helper.avty_t("service"),
                    "json_attr_t": self.mqtt_helper.attr_t("service"),
                    "cmd_t": self.mqtt_helper.cmd_t("service", "snapshot_update_interval"),
                    "unit_of_measurement": "s",
                    "min": 1,
                    "max": 3600,
                    "step": 1,
                    "icon": "mdi:lightning-bolt",
                    "device": device_block,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.mqtt_helper.safe_publish(
            topic=self.mqtt_helper.disc_t("button", "refresh_device_list"),
            payload=json.dumps(
                {
                    "name": f"{self.service_name} Refresh Device List",
                    "uniq_id": self.mqtt_helper.svc_unique_id("refresh_device_list"),
                    "avty_t": self.mqtt_helper.avty_t("service"),
                    "cmd_t": self.mqtt_helper.cmd_t("service", "refresh_device_list", "command"),
                    "payload_press": "refresh",
                    "icon": "mdi:refresh",
                    "device": device_block,
                }
            ),
            qos=self.mqtt_config["qos"],
            retain=True,
        )
        self.logger.debug(f"[HA] Discovery published for {self.service} ({self.mqtt_helper.service_slug})")

    def publish_service_availability(self: Blink2Mqtt, status: str = "online") -> None:
        self.mqtt_helper.safe_publish(self.mqtt_helper.avty_t("service"), status, qos=self.qos, retain=True)

    def publish_service_state(self: Blink2Mqtt) -> None:
        service = {
            "api_calls": self.get_api_calls(),
            "last_api_call": self.get_last_call_date(),
            "device_update_interval": self.device_interval,
            "device_rescan_interval": self.device_list_interval,
            "snapshot_update_interval": self.snapshot_update_interval,
            "rate_limited": "YES" if self.is_rate_limited() else "NO",
        }

        for key, value in service.items():
            self.mqtt_helper.safe_publish(
                self.mqtt_helper.stat_t("service", "service", key),
                json.dumps(value) if isinstance(value, dict) else str(value),
                qos=self.mqtt_config["qos"],
                retain=True,
            )

    # Devices -------------------------------------------------------------------------------------

    def publish_device_discovery(self: Blink2Mqtt, device_id: str) -> None:
        def _publish_one(dev_id: str, defn: dict, suffix: str = "") -> None:
            eff_device_id = dev_id if not suffix else f"{dev_id}_{suffix}"
            topic = self.mqtt_helper.disc_t(defn["component_type"], f"{dev_id}_{suffix}" if suffix else dev_id)
            payload = {k: v for k, v in defn.items() if k != "component_type"}
            self.mqtt_helper.safe_publish(topic, json.dumps(payload), retain=True)
            self.upsert_state(eff_device_id, internal={"discovered": True})

        component = self.get_component(device_id)
        _publish_one(device_id, component, suffix="")

        modes = self.get_modes(device_id)
        for slug, mode in modes.items():
            _publish_one(device_id, mode, suffix=slug)

    def publish_device_availability(self: Blink2Mqtt, device_id: str, online: bool = True) -> None:
        payload = "online" if online else "offline"

        avty_t = self.get_device_availability_topic(device_id)
        self.mqtt_helper.safe_publish(avty_t, payload, retain=True)

    def publish_device_state(self: Blink2Mqtt, device_id: str) -> None:
        def _publish_one(dev_id: str, defn: str | dict[str, Any], suffix: str = "") -> None:
            topic = self.get_device_state_topic(dev_id, suffix)
            if isinstance(defn, dict):
                flat: dict[str, Any] = {k: v for k, v in defn.items() if k != "component_type"}
                meta = self.states[dev_id].get("meta")
                if isinstance(meta, dict) and "last_update" in meta:
                    flat["last_update"] = meta["last_update"]
                self.mqtt_helper.safe_publish(topic, json.dumps(flat), retain=True)
            else:
                self.mqtt_helper.safe_publish(topic, defn, retain=True)

        if not self.is_discovered(device_id):
            self.logger.debug(f"[device state] Discovery not complete for {device_id} yet, holding off on sending state")
            return

        states = self.states[device_id]
        _publish_one(device_id, states[self.get_component_type(device_id)])

        modes = self.get_modes(device_id)
        for name, mode in modes.items():
            component_type = mode["component_type"]

            # if no state yet, skip it
            if component_type not in states or (isinstance(states[component_type], dict) and name not in states[component_type]):
                continue

            type_states = states[component_type][name] if isinstance(states[component_type], dict) else states[component_type]
            _publish_one(device_id, type_states, name)

    def publish_device_image(self: Blink2Mqtt, device_id: str, type: str) -> None:
        payload = self.states[device_id][type]
        if payload and isinstance(payload, str):
            self.logger.info(f"Updating {self.get_device_name(device_id)} with latest snapshot")
            topic = self.get_device_image_topic(device_id)
            self.mqtt_helper.safe_publish(topic, payload, retain=True)
