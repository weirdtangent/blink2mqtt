# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class RefreshMixin:
    async def refresh_all_devices(self: "Blink2Mqtt") -> None:
        self.logger.info(f"refreshing all devices from Blink (every {self.device_interval} sec)")
        await self.blink_refresh()

        # get the latests device states from Blink
        blink_devices = await self.get_cameras()
        sync_modules = await self.get_sync_modules()

        async def handle_camera(device_id: str, cfg: dict[str, Any]) -> None:
            await self.build_camera_states(device_id, cfg)
            await self.publish_device_state(device_id)

        async def handle_sync_module(device_id: str, cfg: dict[str, Any]) -> None:
            await self.build_sync_module_states(device_id, cfg)
            await self.publish_device_state(device_id)

        tasks = [
            *(handle_sync_module(device_id, device) for device_id, device in sync_modules.items()),
            *(handle_camera(device_id, device) for device_id, device in blink_devices.items()),
        ]
        await asyncio.gather(*tasks)

    async def refresh_snapshot_all_devices(self: "Blink2Mqtt") -> None:
        self.logger.info(f"requesting snapshots from cameras (every {self.snapshot_update_interval} sec)")

        tasks1 = []
        tasks2 = []
        for device_id in self.blink_cameras:
            tasks1.append(asyncio.create_task(self.take_snapshot_from_device(device_id)))
            tasks2.append(asyncio.create_task(self.refresh_snapshot(device_id, "snapshot")))

        await asyncio.gather(*tasks1)
        await asyncio.sleep(3)  # Blink says to give them 2-5 seconds
        await self.blink_refresh()
        await asyncio.gather(*tasks2)

    async def refresh_snapshot(self: "Blink2Mqtt", device_id: str, type: str) -> None:
        states = self.states[device_id]
        image = await self.get_snapshot_from_device(device_id)

        # only store and send to MQTT if we got an image AND the image has changed
        if image and (type not in states or states[type] is None or states[type] != image):
            states[type] = image
            self.upsert_state(device_id, sensor={"last_event": "Timed snapshot", "last_event_time": datetime.now(timezone.utc).isoformat()})
            await asyncio.gather(self.publish_device_state(device_id), self.publish_device_image(device_id, type))
