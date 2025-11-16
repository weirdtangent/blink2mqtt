# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import argparse
import asyncio
from blinkpy.blinkpy import Blink
import concurrent.futures
from datetime import datetime
import logging
from json_logging import get_logger
from mqtt_helper import MqttHelper
from paho.mqtt.client import Client
from types import TracebackType

from typing import Any, Self, cast

from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class Base:
    def __init__(self: Blink2Mqtt, args: argparse.Namespace | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.loop = asyncio.get_running_loop()
        self.loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=16))

        self.args = args
        self.logger = get_logger(__name__)

        # now load self.config right away
        cfg_arg = getattr(args, "config", None)
        self.config = self.load_config(cfg_arg)

        if not self.config["mqtt"] or not self.config["blink"]:
            raise ValueError("config was not loaded")

        # down in trenches if we have to
        if self.config.get("debug"):
            self.logger.setLevel(logging.DEBUG)

        self.mqtt_config = self.config["mqtt"]
        self.blink_config = self.config["blink"]

        self.service = self.mqtt_config["prefix"]
        self.service_name = f"{self.service} service"
        self.qos = self.mqtt_config["qos"]

        self.mqtt_helper = MqttHelper(self.service, default_qos=self.qos, default_retain=True)

        self.running = False
        self.discovery_complete = False

        self.blink_cameras: dict[str, dict[str, Any]] = {}
        self.blink_sync_modules: dict[str, dict[str, Any]] = {}
        self.devices: dict[str, Any] = {}
        self.states: dict[str, Any] = {}
        self.events: list[str] = []

        self.mqttc: Client
        self.mqtt_connect_time: datetime
        self.client_id = self.mqtt_helper.client_id()

        self.session: Any = None
        self.blink: Blink
        self.api_calls = 0
        self.last_call_date = ""
        self.rate_limited = False

        self.device_interval = self.blink_config["device_interval"]
        self.device_list_interval = self.blink_config["device_list_interval"]
        self.snapshot_update_interval = self.blink_config["snapshot_update_interval"]

    async def __aenter__(self: Self) -> Blink2Mqtt:
        super_enter = getattr(super(), "__enter__", None)
        if callable(super_enter):
            super_enter()

        await cast(Any, self).mqttc_create()
        self.running = True

        return cast(Blink2Mqtt, self)

    async def __aexit__(self: Self, exc_type: BaseException | None, exc_val: BaseException | None, exc_tb: TracebackType) -> None:
        super_exit = getattr(super(), "__exit__", None)
        if callable(super_exit):
            super_exit(exc_type, exc_val, exc_tb)

        self.running = False

        if self.session and not self.session.closed:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                loop.create_task(self.session.close())
            else:
                asyncio.run(self.session.close())

        if cast(Any, self).mqttc is not None:
            try:
                await cast(Any, self).publish_service_availability("offline")
                cast(Any, self).mqttc.loop_stop()
            except Exception as e:
                self.logger.debug(f"MQTT loop_stop failed: {e}")

            if cast(Any, self).mqttc.is_connected():
                try:
                    cast(Any, self).mqttc.disconnect()
                    self.logger.info("Disconnected from MQTT broker")
                except Exception as e:
                    self.logger.warning(f"Error during MQTT disconnect: {e}")

        self.logger.info("Exiting gracefully")
