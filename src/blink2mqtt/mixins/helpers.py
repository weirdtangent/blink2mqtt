# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from deepmerge import Merger
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from blink2mqtt.core import Blink2Mqtt
    from blink2mqtt.interface import BlinkServiceProtocol


class HelpersMixin:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    def build_camera_states(self: Blink2Mqtt, device_id: str, camera: list[str, str]) -> None:
        self.upsert_state(
            device_id,
            switch={
                "motion_detection": "ON" if camera["motion_detection"] else "OFF",
            },
            sensor={
                "battery_status": camera["battery"],
                "temperature": camera["temperature"],
                "wifi_signal": camera["wifi_strength"],
                "last_event": "",
                "last_event_time": "",
            },
            binary_sensor={
                "motion": camera["motion"],
            },
        )

    def build_sync_module_states(self: Blink2Mqtt, device_id: str, sync_module: list[str, str]) -> None:
        self.upsert_state(
            device_id,
            switch={"armed": "ON" if sync_module["arm_mode"] else "OFF"},
            sensor={"local_storage": sync_module["local_storage"]},
        )

    # send command to Blink -----------------------------------------------------------------------

    async def send_command(self: Blink2Mqtt, device_id: str, payload: str, attribute: str) -> None:
        if device_id == "service":
            self.logger.error(f'Why are you trying to send {payload} to the "service"? Ignoring you.')
            return

        self.logger.info(f"{device_id} ; {payload} ; {attribute}")
        match attribute:
            case "motion_detection":
                # lets update HA, assuming it will work, but remember prior state in case we have to go back
                was = self.states[device_id]["sensor"][attribute]
                self.upsert_state(device_id, switch={"motion_detection": payload})
                self.logger.info(f"sending {device_id} motion_detection to {payload} command to Blink")
                self.publish_device_state(device_id)
                success = await self.set_motion_detection(device_id, "ON" if payload else "OFF")
                if not success:
                    self.logger.error(f"setting {device_id} motion_detection to {payload} failed")
                    self.upsert_state(device_id, switch={"motion_detection": was})
                    self.publish_device_state(device_id)
            case _:
                self.logger.error(f"Received command for unknown: {attribute} with payload {payload}")

    def handle_service_message(self: Blink2Mqtt, handler: str, message: str) -> None:
        match handler:
            case "device_update_interval":
                self.device_interval = message
                self.logger.debug(f"device_interval updated to be {message}")
            case "device_rescan_interval":
                self.device_list_interval = message
                self.logger.debug(f"device_list_interval updated to be {message}")
            case "snapshot_update_interval":
                self.snapshot_update_interval = message
                self.logger.debug(f"snapshot_update_interval updated to be {message}")
            case "refresh_device_list":
                if message == "refresh":
                    self.rediscover_all()
                else:
                    self.logger.error("[handler] unknown [message]")
                    return
            case _:
                self.logger.error(f"Unrecognized message to {handler} -> {message}")
                return
        self.publish_service_state()

    def rediscover_all(self: Blink2Mqtt) -> None:
        self.publish_service_state()
        self.publish_service_discovery()
        for device_id in self.devices:
            if device_id == "service":
                continue
            self.publish_device_state(device_id)
            self.publish_device_discovery(device_id)

    # Upsert devices and states -------------------------------------------------------------------

    MERGER = Merger(
        [(dict, "merge"), (list, "append_unique"), (set, "union")],
        ["override"],  # type conflicts: new wins
        ["override"],  # fallback
    )

    def _assert_no_tuples(self: Blink2Mqtt, data, path="root"):
        """Recursively check for tuples in both keys and values of dicts/lists."""
        if isinstance(data, tuple):
            raise TypeError(f"⚠️ Found tuple at {path}: {data!r}")

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(key, tuple):
                    raise TypeError(f"⚠️ Found tuple key at {path}: {key!r}")
                self._assert_no_tuples(value, f"{path}.{key}")
        elif isinstance(data, list):
            for idx, value in enumerate(data):
                self._assert_no_tuples(value, f"{path}[{idx}]")

    def upsert_device(self: Blink2Mqtt, device_id: str, **kwargs: dict[str, Any] | str | int | bool) -> None:
        for section, data in kwargs.items():
            # Pre-merge check
            self._assert_no_tuples(data, f"device[{device_id}].{section}")
            merged = self.MERGER.merge(self.devices.get(device_id, {}), {section: data})
            # Post-merge check
            self._assert_no_tuples(merged, f"device[{device_id}].{section} (post-merge)")
            self.devices[device_id] = merged

    def upsert_state(self: Blink2Mqtt, device_id, **kwargs: dict[str, Any] | str | int | bool) -> None:
        for section, data in kwargs.items():
            self._assert_no_tuples(data, f"state[{device_id}].{section}")
            merged = self.MERGER.merge(self.states.get(device_id, {}), {section: data})
            self._assert_no_tuples(merged, f"state[{device_id}].{section} (post-merge)")
            self.states[device_id] = merged
