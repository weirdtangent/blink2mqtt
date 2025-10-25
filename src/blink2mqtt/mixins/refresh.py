# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blink2mqtt.core import Blink2Mqtt
    from blink2mqtt.interface import BlinkServiceProtocol


class RefreshMixin:
    if TYPE_CHECKING:
        self: "BlinkServiceProtocol"

    async def refresh_all_devices(self: "Blink2Mqtt") -> None:
        self.logger.info(f"Refreshing all devices from Blink (every {self.device_interval} sec)")
        await self.blink_refresh()

        blink_devices = await self.get_cameras()
        sync_modules = await self.get_sync_modules()

        for device_id in sync_modules:
            sync_module = sync_modules[device_id]["config"]
            self.build_sync_module_states(device_id, sync_module)
            self.publish_device_state(device_id)

        for device_id in blink_devices:
            camera = blink_devices[device_id]["config"]
            self.build_camera_states(device_id, camera)
            self.publish_device_state(device_id)

    async def refresh_snapshot_all_devices(self: "Blink2Mqtt") -> None:
        self.logger.info(f"Requesting snapshots on devices (every {self.snapshot_update_interval} sec)")
        await self.blink_refresh()

        tasks1 = []
        tasks2 = []
        for device_id in self.devices:
            if self.get_component_type(device_id) == "camera" and self.is_discovered(device_id):
                tasks1.append(asyncio.create_task(self.take_snapshot_from_device(device_id)))
                tasks2.append(asyncio.create_task(self.refresh_snapshot(device_id, "snapshot")))

        await asyncio.gather(*tasks1)
        await asyncio.gather(*tasks2)

    async def refresh_snapshot(self: "Blink2Mqtt", device_id: str, type: str) -> None:
        states = self.states[device_id]

        image = await self.get_snapshot_from_device(device_id)

        # only store and send to MQTT if we got an image AND the image has changed
        if image and (states[type] is None or states[type] != image):
            states[type] = image
            self.publish_device_image(device_id, type)
