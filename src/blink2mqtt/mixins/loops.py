# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
import signal
import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.core import Blink2Mqtt
    from blink2mqtt.interface import BlinkServiceProtocol


class LoopsMixin:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    async def device_list_loop(self: Blink2Mqtt) -> None:
        while self.running:
            try:
                await asyncio.sleep(self.device_list_interval)
                await self.refresh_device_list()
            except asyncio.CancelledError:
                self.logger.debug("device_list_loop cancelled during sleep")
                break

    async def device_loop(self: Blink2Mqtt) -> None:
        while self.running:
            try:
                await asyncio.sleep(self.device_interval)
                await self.refresh_all_devices()
            except asyncio.CancelledError:
                self.logger.debug("device_loop cancelled during sleep")
                break

    async def collect_snapshots_loop(self: Blink2Mqtt) -> None:
        while self.running:
            try:
                await asyncio.sleep(self.snapshot_update_interval)
                await self.refresh_snapshot_all_devices()
            except asyncio.CancelledError:
                self.logger.debug("snapshot_loop cancelled during sleep")
                break

    async def collect_events_loop(self: Blink2Mqtt) -> None:
        while self.running:
            try:
                await asyncio.sleep(1)
                await self.collect_all_blink_events()
            except asyncio.CancelledError:
                self.logger.debug("collect_events_loop cancelled during sleep")
                break

    async def process_events_loop(self: Blink2Mqtt) -> None:
        while self.running:
            try:
                await asyncio.sleep(1)
                await self.process_events()
            except asyncio.CancelledError:
                self.logger.debug("process_events_loop cancelled during sleep")
                break

    async def heartbeat(self: Blink2Mqtt) -> None:
        while self.running:
            try:
                await asyncio.sleep(60)
                self.heartbeat_ready()
            except asyncio.CancelledError:
                self.logger.debug("heartbeat cancelled during sleep")
                break

    def _handle_signal(self: Blink2Mqtt, signum, frame=None):
        sig_name = signal.Signals(signum).name
        self.logger.warning(f"{sig_name} received - stopping service loop")
        self.running = False

        def _force_exit():
            self.logger.warning("Force-exiting process after signal")
            os._exit(0)

        threading.Timer(5.0, _force_exit).start()

    # main loop
    async def main_loop(self: Blink2Mqtt) -> None:
        self.loop = asyncio.get_running_loop()

        # connect, get sync modules and cameras, and get first snapshots
        await self.connect()
        await self.refresh_device_list()
        await self.refresh_snapshot_all_devices()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._handle_signal)
            except Exception:
                self.logger.debug(f"Cannot install handler for {sig}")

        self.running = True
        self.mark_ready()
        self.logger.info(
            f"starting refresh loops: devices at {self.device_interval}, list at {self.device_list_interval}, snapshots at {self.snapshot_update_interval}"
        )

        tasks = [
            asyncio.create_task(self.device_list_loop(), name="device_list_loop"),
            asyncio.create_task(self.device_loop(), name="device_loop"),
            asyncio.create_task(self.collect_snapshots_loop(), name="collect_snapshots_loop"),
            # turned off while the API is unknown - Blink's 09/2025 update broke the endpoint being used (they moved it somewhere/replaced it/whatever)
            # asyncio.create_task(self.collect_events_loop(), name="collect_events_loop"),
            # asyncio.create_task(self.process_events_loop(), name="process_events_loop"),
            asyncio.create_task(self.heartbeat(), name="heartbeat"),
        ]

        try:
            results = await asyncio.gather(*tasks)
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"Task raised exception: {result}", exc_info=True)
                    self.running = False
        except asyncio.CancelledError:
            self.logger.warning("Main loop cancelled — shutting down...")
        except Exception as err:
            self.logger.exception(f"Unhandled exception in main loop: {err}")
            self.running = False
        finally:
            self.logger.info("All loops terminated — cleanup complete.")
