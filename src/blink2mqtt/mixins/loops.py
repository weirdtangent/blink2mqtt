# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from __future__ import annotations

import asyncio
import signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class LoopsMixin:
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
                await asyncio.sleep(60)
                now = self.loop.time()
                due_device_ids: list[str] = []
                for device_id, camera in self.blink_cameras.items():
                    internal = self.states.setdefault(device_id, {}).setdefault("internal", {})
                    last_snapshot = float(internal.get("last_snapshot", 0.0))

                    battery_status = camera.get("battery")
                    if not battery_status:
                        interval_seconds = self.snapshot_interval_wired_minutes * 60
                    else:
                        if self.snapshot_interval_battery_hours == 0:
                            continue
                        interval_seconds = self.snapshot_interval_battery_hours * 3600

                    if (now - last_snapshot) >= interval_seconds:
                        due_device_ids.append(device_id)

                if due_device_ids:
                    await self.refresh_snapshot_devices(due_device_ids)
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

    async def cleanup_snapshots_loop(self: Blink2Mqtt) -> None:
        while self.running:
            try:
                await self.cleanup_old_snapshots()
            except asyncio.CancelledError:
                self.logger.debug("cleanup_snapshots_loop cancelled during cleanup")
                break
            except Exception:
                self.logger.exception("unexpected error during cleanup_old_snapshots; continuing")
            try:
                await asyncio.sleep(86400)  # once per day
            except asyncio.CancelledError:
                self.logger.debug("cleanup_snapshots_loop cancelled during sleep")
                break

    async def heartbeat(self: Blink2Mqtt) -> None:
        while self.running:
            try:
                await asyncio.sleep(60)
                self.heartbeat_ready()
            except asyncio.CancelledError:
                self.logger.debug("heartbeat cancelled during sleep")
                break

    # main loop
    async def main_loop(self: Blink2Mqtt) -> None:
        # connect, get sync modules and cameras, and get first snapshots
        await self.connect()
        await self.refresh_device_list()
        await self.refresh_snapshot_all_devices()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self.handle_signal)
            except Exception:
                self.logger.debug(f"cannot install handler for {sig}")

        self.running = True
        self.mark_ready()

        tasks = [
            asyncio.create_task(self.device_list_loop(), name="device_list_loop"),
            asyncio.create_task(self.device_loop(), name="device_loop"),
            asyncio.create_task(self.collect_snapshots_loop(), name="collect_snapshots_loop"),
            # turned off while the API is unknown - Blink's 09/2025 update broke the endpoint being used (they moved it somewhere/replaced it/whatever)
            # asyncio.create_task(self.collect_events_loop(), name="collect_events_loop"),
            # asyncio.create_task(self.process_events_loop(), name="process_events_loop"),
            asyncio.create_task(self.cleanup_snapshots_loop(), name="cleanup_snapshots_loop"),
            asyncio.create_task(self.heartbeat(), name="heartbeat"),
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            self.logger.warning("main loop cancelled — shutting down...")
        except Exception as err:
            self.logger.exception(f"unhandled exception in main loop: {err}")
            self.running = False
        finally:
            self.logger.info("all loops terminated — cleanup complete.")
