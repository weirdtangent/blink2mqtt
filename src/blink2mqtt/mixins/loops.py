# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
import signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.core import Blink2Mqtt
    from blink2mqtt.interface import BlinkServiceProtocol


class LoopsMixin:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    async def device_list_loop(self: Blink2Mqtt) -> None:
        while self.running:
            if self.discovery_complete:
                await self.refresh_device_list()
            try:
                await asyncio.sleep(self.device_list_interval)
            except asyncio.CancelledError:
                self.logger.debug("device_list_loop cancelled during sleep")
                break

    async def device_loop(self: Blink2Mqtt) -> None:
        while self.running:
            if self.discovery_complete:
                await self.refresh_all_devices()
            try:
                await asyncio.sleep(self.device_interval)
            except asyncio.CancelledError:
                self.logger.debug("device_loop cancelled during sleep")
                break

    async def collect_snapshots_loop(self: Blink2Mqtt) -> None:
        while self.running:
            if self.discovery_complete:
                await self.collect_snapshots()
            try:
                await asyncio.sleep(self.snapshot_update_interval)
            except asyncio.CancelledError:
                self.logger.debug("snapshot_loop cancelled during sleep")
                break

    async def heartbeat(self: Blink2Mqtt) -> None:
        while self.running:
            self.heartbeat_ready()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                self.logger.debug("heartbeat cancelled during sleep")
                break

    # main loop
    async def main_loop(self: Blink2Mqtt) -> None:
        self.loop = asyncio.get_running_loop()
        await self.connect()

        await self.refresh_device_list()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._handle_signal)
            except Exception:
                self.logger.debug(f"Cannot install handler for {sig}")

        self.running = True
        self.mark_ready()

        tasks = [
            asyncio.create_task(self.device_list_loop(), name="device_list_loop"),
            asyncio.create_task(self.device_loop(), name="device_loop"),
            asyncio.create_task(
                self.collect_snapshots_loop(), name="collect_snapshots_loop"
            ),
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
