# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import os
import signal
import threading
from deepmerge import Merger


class HelpersMixin:
    def build_device_states(self, states, raw_id):
        return

    # convert MQTT attributes to Blink capabilities
    def build_blink_capabilities(self, device_id, attributes):
        return

    def _extract_scalar(self, val):
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

    def send_command(self, device_id, response):
        if device_id == "service":
            self.logger.error(
                f'Why are you trying to send {response} to the "service"? Ignoring you.'
            )
            return
        states = self.states.get(device_id, None)
        raw_id = self.get_raw_id(device_id)

        capabilities = self.build_blink_capabilities(device_id, response)
        if not capabilities:
            self.logger.debug(
                f"No set of capabilities built to send Blink for {device_id}"
            )
            return

        need_boost = False
        for key in capabilities:
            response = self.blink.send_command(
                raw_id,
                capabilities[key]["type"],
                capabilities[key]["instance"],
                capabilities[key]["value"],
            )
            self.publish_service_state()

            # no need to boost-refresh if we get the state back on the successful command response
            if len(response) > 0:
                self.build_device_states(states, raw_id)

                # now that we've used the data, lets remove the chunky
                # `lastUpdate` key and then dump the rest into the log
                response.pop("lastUpdate", None)
                self.logger.debug(f"Got Blink response from command: {response}")

                self.publish_device_state(device_id)

                # remove from boosted list (if there), since we got a change
                if device_id in self.boosted:
                    self.boosted.remove(device_id)
            else:
                self.logger.info(f"Did not find changes in Blink response: {response}")
                need_boost = True

        # if we send a command and did not get a state change back on the response
        # lets boost this device to refresh it, just in case
        if need_boost and device_id not in self.boosted:
            self.boosted.append(device_id)

    def handle_service_message(self, handler, message):
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

    def rediscover_all(self):
        self.publish_service_state()
        self.publish_service_discovery()
        for device_id in self.devices:
            if device_id == "service":
                continue
            self.publish_device_state(device_id)
            self.publish_device_discovery(device_id)

    # Utility functions ---------------------------------------------------------------------------

    def _install_signal_handlers(self):
        """Install very simple shutdown handlers (used in Docker)."""
        try:
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
        except Exception:
            self.logger.debug("Signal handlers not supported on this platform")

    def _handle_signal(self, signum, frame=None):
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

    def assert_no_tuples(self, data, path="root"):
        """Recursively check for tuples in both keys and values of dicts/lists."""
        if isinstance(data, tuple):
            raise TypeError(f"⚠️ Found tuple at {path}: {data!r}")

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(key, tuple):
                    raise TypeError(f"⚠️ Found tuple key at {path}: {key!r}")
                self.assert_no_tuples(value, f"{path}.{key}")
        elif isinstance(data, list):
            for idx, value in enumerate(data):
                self.assert_no_tuples(value, f"{path}[{idx}]")

    def upsert_device(self, device_id, **kwargs):
        for section, data in kwargs.items():
            # Pre-merge check
            self.assert_no_tuples(data, f"device[{device_id}].{section}")
            merged = self.MERGER.merge(self.devices.get(device_id, {}), {section: data})
            # Post-merge check
            self.assert_no_tuples(merged, f"device[{device_id}].{section} (post-merge)")
            self.devices[device_id] = merged

    def upsert_state(self, device_id, **kwargs):
        for section, data in kwargs.items():
            self.assert_no_tuples(data, f"state[{device_id}].{section}")
            merged = self.MERGER.merge(self.states.get(device_id, {}), {section: data})
            self.assert_no_tuples(merged, f"state[{device_id}].{section} (post-merge)")
            self.states[device_id] = merged
