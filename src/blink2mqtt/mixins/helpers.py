# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import os
import signal
import threading
from deepmerge import Merger
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from blink2mqtt.core import Blink2Mqtt
    from blink2mqtt.interface import BlinkServiceProtocol


class HelpersMixin:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    def build_device_states(self: Blink2Mqtt, states: str, raw_id: str) -> None:
        return

    # convert MQTT attributes to Blink capabilities
    def build_blink_capabilities(
        self: Blink2Mqtt, device_id: str, attributes: list
    ) -> None:
        return

    def _extract_scalar(self: Blink2Mqtt, val):
        """Try to get a representative scalar from arbitrary API data."""
        # direct primitive
        if isinstance(val, (int, float, str, bool)):
            return val

        # dict: look for a likely scalar value
        if isinstance(val, dict):
            for v in val.values():
                if isinstance(v, (int, float, str, bool)):
                    return v
            return None

        # list: prefer first simple element
        if isinstance(val, list) and val:
            for v in val:
                if isinstance(v, (int, float, str, bool)):
                    return v
            return None

        return None

    # send command to Blink -----------------------------------------------------------------------

    async def send_command(
        self: Blink2Mqtt, device_id: str, payload: str, attribute: str
    ) -> None:
        if device_id == "service":
            self.logger.error(
                f'Why are you trying to send {payload} to the "service"? Ignoring you.'
            )
            return

        self.logger.info(f"{device_id} ; {payload} ; {attribute}")
        match attribute:
            case "motion_detections":
                response = await self.set_motion_detection(device_id, (payload == "ON"))
                self.logger.info(response)
            case _:
                self.logger.error(
                    f"Received command for unknown: {attribute} with payload {payload}"
                )

    def handle_service_message(self: Blink2Mqtt, handler: str, message: str) -> None:
        match handler:
            case "device_refresh":
                self.device_interval = message
            case "device_list_refresh":
                self.device_list_interval = message
            case "snapshot_refresh":
                self.snapshot_update_interval = message
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

    # Utility functions ---------------------------------------------------------------------------

    def _install_signal_handlers(self: Blink2Mqtt):
        """Install very simple shutdown handlers (used in Docker)."""
        try:
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
        except Exception:
            self.logger.debug("Signal handlers not supported on this platform")

    def _handle_signal(self: Blink2Mqtt, signum, frame=None):
        """Handle SIGTERM/SIGINT and exit cleanly or forcefully."""
        sig_name = signal.Signals(signum).name
        self.logger.warning(f"{sig_name} received - stopping service loop")
        self.running = False

        def _force_exit():
            self.logger.warning("Force-exiting process after signal")
            os._exit(0)

        threading.Timer(5.0, _force_exit).start()

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

    def upsert_device(
        self: Blink2Mqtt, device_id: str, **kwargs: dict[str, Any] | str | int | bool
    ) -> None:
        for section, data in kwargs.items():
            # Pre-merge check
            self._assert_no_tuples(data, f"device[{device_id}].{section}")
            merged = self.MERGER.merge(self.devices.get(device_id, {}), {section: data})
            # Post-merge check
            self._assert_no_tuples(
                merged, f"device[{device_id}].{section} (post-merge)"
            )
            self.devices[device_id] = merged

    def upsert_state(
        self: Blink2Mqtt, device_id, **kwargs: dict[str, Any] | str | int | bool
    ) -> None:
        for section, data in kwargs.items():
            self._assert_no_tuples(data, f"state[{device_id}].{section}")
            merged = self.MERGER.merge(self.states.get(device_id, {}), {section: data})
            self._assert_no_tuples(merged, f"state[{device_id}].{section} (post-merge)")
            self.states[device_id] = merged
