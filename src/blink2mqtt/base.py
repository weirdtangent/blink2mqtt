# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import argparse
import logging
from json_logging import get_logger

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol


class Base:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    def __init__(self, *, args: argparse.Namespace | None = None, **kwargs):
        super().__init__(**kwargs)

        self.args = args
        self.logger = get_logger(__name__)

        # and quiet down some others
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("blinkpy.blinkpy").setLevel(logging.WARNING)

        # now load self.config right away
        cfg_arg = getattr(args, "config", None)
        self.config = self.load_config(cfg_arg)

        if not self.config["mqtt"] or not self.config["blink"]:
            raise ValueError("config was not loaded")

        # down in trenches if we have to
        if self.config.get("debug"):
            self.logger.setLevel(logging.DEBUG)

        self.running = False
        self.discovery_complete = False
        self.loop = None

        self.mqtt_config = self.config["mqtt"]
        self.blink_config = self.config["blink"]

        self.devices = {}
        self.states = {}

        self.mqttc = None
        self.mqtt_connect_time = None
        self.client_id = self.get_new_client_id()

        self.service = self.mqtt_config["prefix"]
        self.service_name = f"{self.service} service"
        self.service_slug = self.service

        self.qos = self.mqtt_config["qos"]

        self.session = None
        self.blink = None
        self.blink_cameras = {}
        self.blink_sync_modules = {}
        self.api_calls = 0
        self.last_call_date = None
        self.rate_limited = False

        self.device_interval = self.blink_config["device_interval"]
        self.device_list_interval = self.blink_config["device_list_interval"]
        self.snapshot_update_interval = self.blink_config["snapshot_update_interval"]

    def __enter__(self):
        super_enter = getattr(super(), "__enter__", None)
        if callable(super_enter):
            super_enter()

        self.mqttc_create()
        self.running = True

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super_exit = getattr(super(), "__exit__", None)
        if callable(super_exit):
            super_exit(exc_type, exc_val, exc_tb)

        self.running = False

        if self.mqttc is not None:
            try:
                self.publish_service_availability("offline")
                self.mqttc.loop_stop()
            except Exception as e:
                self.logger.debug(f"MQTT loop_stop failed: {e}")

            if self.mqttc.is_connected():
                try:
                    self.mqttc.disconnect()
                    self.logger.info("Disconnected from MQTT broker")
                except Exception as e:
                    self.logger.warning(f"Error during MQTT disconnect: {e}")

        self.logger.info("Exiting gracefully")
