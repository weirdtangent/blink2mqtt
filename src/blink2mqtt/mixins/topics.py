# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from typing import TYPE_CHECKING, cast, Any

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class TopicsMixin:

    # Device properties ---------------------------------------------------------------------------

    def get_device_name(self: Blink2Mqtt, device_id: str) -> str:
        return cast(str, self.devices[device_id]["component"]["device"]["name"])

    def get_component(self: Blink2Mqtt, device_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self.devices[device_id]["component"])

    def get_component_type(self: Blink2Mqtt, device_id: str) -> str:
        return cast(str, self.devices[device_id]["component"].get("component_type", "unknown"))

    def get_modes(self: Blink2Mqtt, device_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self.devices[device_id]["modes"])

    def get_mode(self: Blink2Mqtt, device_id: str, mode_name: str) -> dict[str, Any]:
        return cast(dict[str, Any], self.devices[device_id]["modes"][mode_name])

    def is_discovered(self: Blink2Mqtt, device_id: str) -> bool:
        return cast(bool, self.states[device_id]["internal"].get("discovered", False))

    def get_device_state_topic(self: Blink2Mqtt, device_id: str, mode_name: str = "") -> str:
        component = self.get_mode(device_id, mode_name) if mode_name else self.get_component(device_id)

        if component["component_type"] == "camera":
            return cast(str, component["json_attributes_topic"])
        else:
            return cast(str, component.get("stat_t") or component.get("state_topic"))

    def get_device_image_topic(self: Blink2Mqtt, device_id: str) -> str:
        component = self.get_component(device_id)
        return cast(str, component["topic"])

    def get_device_availability_topic(self: Blink2Mqtt, device_id: str) -> str:
        component = self.get_component(device_id)
        return cast(str, component.get("avty_t") or component.get("availability_topic"))

    def get_device_discovery_topic(self: Blink2Mqtt, device_id: str) -> str:
        component = self.get_component(device_id)
        return cast(str, component.get("disc_t") or component.get("discovery_topic"))
