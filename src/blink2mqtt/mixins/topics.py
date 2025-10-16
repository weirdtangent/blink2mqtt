# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import random
import string
from typing import Optional


class TopicsMixin:
    def get_new_client_id(self):
        return (
            self.mqtt_config["prefix"]
            + "-"
            + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        )

    # Slug strings --------------------------------------------------------------------------------

    def get_device_slug(self, device_id: str, type: Optional[str] = None) -> str:
        return "_".join(
            filter(None, [self.service_slug, device_id.replace(":", ""), type])
        )

    def get_vendor_device_slug(self, device_id):
        return f"{self.service_slug}-{device_id.replace(':', '')}"

    # Topic strings -------------------------------------------------------------------------------

    def get_service_device(self):
        return self.service

    def get_service_topic(self, topic):
        return f"{self.service_slug}/status/{topic}"

    def get_device_topic(self, component_type, device_id, *parts) -> str:
        if device_id == "service":
            return "/".join([self.service_slug, *map(str, parts)])

        device_slug = self.get_device_slug(device_id)
        return "/".join(
            [self.service_slug, component_type, device_slug, *map(str, parts)]
        )

    def get_discovery_topic(self, component, item) -> str:
        return f"{self.mqtt_config['discovery_prefix']}/{component}/{item}/config"

    def get_state_topic(self, device_id, category, item=None) -> str:
        topic = (
            f"{self.service_slug}/{category}"
            if device_id == "service"
            else f"{self.service_slug}/devices/{self.get_device_slug(device_id)}/{category}"
        )
        return f"{topic}/{item}" if item else topic

    def get_availability_topic(
        self, device_id, category="availability", item=None
    ) -> str:
        topic = (
            f"{self.service_slug}/{category}"
            if device_id == "service"
            else f"{self.service_slug}/devices/{self.get_device_slug(device_id)}/{category}"
        )
        return f"{topic}/{item}" if item else topic

    def get_attribute_topic(self, device_id, category, item, attribute) -> str:
        if device_id == "service":
            return f"{self.service_slug}/{category}/{item}/{attribute}"

        device_entry = self.devices.get(device_id, {})
        component = (
            device_entry.get("component")
            or device_entry.get("component_type")
            or category
        )
        return f"{self.mqtt_config['discovery_prefix']}/{component}/{self.get_device_slug(device_id)}/{item}/{attribute}"

    def get_command_topic(self, device_id, category, command="set") -> str:
        if device_id == "service":
            return f"{self.service_slug}/service/{category}/{command}"

        # if category is not passed in, device must exist already
        if not category:
            category = self.devices[device_id]["component"]["component_type"]

        return f"{self.service_slug}/{category}/{self.get_device_slug(device_id)}/{command}"

    # Device propertiesi --------------------------------------------------------------------------

    def get_device_name(self, device_id):
        return self.devices[device_id]["component"]["device"]["name"]

    def get_raw_id(self, device_id):
        return self.states[device_id]["internal"]["raw_id"]

    def get_component(self, device_id):
        return self.devices[device_id].get("component", None)

    def get_component_type(self, device_id):
        return self.devices[device_id]["component"].get("component_type", "unknown")

    def get_modes(self, device_id):
        return self.devices[device_id].get("modes", {})

    def get_mode(self, device_id, mode_name):
        modes = self.devices[device_id].get("modes", {})
        return modes.get(mode_name, {})

    def is_discovered(self, device_id):
        return self.states[device_id]["internal"].get("discovered", False)

    def get_device_state_topic(self, device_id, mode_name=None):
        component = (
            self.get_mode(device_id, mode_name)
            if mode_name
            else self.get_component(device_id)
        )

        if component["component_type"] == "camera":
            return component.get("json_attributes_topic", None)
        else:
            return component.get("stat_t", component.get("state_topic", None))

    def get_device_image_topic(self, device_id):
        component = self.get_component(device_id)
        return component.get("topic", None)

    def get_device_availability_topic(self, device_id):
        component = self.get_component(device_id)
        return component.get("avty_t", component.get("availability_topic", None))

    # Misc helpers --------------------------------------------------------------------------------

    def get_device_block(self, id, name, via=None, sw_version=None, mfr="Amazon"):
        device = {"name": name, "identifiers": [id], "manufacturer": mfr}

        if via:
            device["via_device"] = via
        if sw_version:
            device["sw_version"] = sw_version

        if name == self.service_name:
            device.update(
                {
                    "suggested_area": "House",
                    "manufacturer": "weirdTangent",
                    "sw_version": self.config["version"],
                }
            )
        return device
