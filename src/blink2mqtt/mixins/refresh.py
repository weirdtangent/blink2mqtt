# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
from asyncio import timeout


class RefreshMixin:
    async def refresh_all_devices(self):
        # don't let this kick off until we are done with our list
        while not self.discovery_complete and self.running:
            await asyncio.sleep(1)

        self.logger.info(
            f"Refreshing all devices from Blink (every {self.device_interval} sec)"
        )

        for device_id in self.devices:
            if not self.running:
                break
            if device_id == "service" or device_id in self.boosted:
                continue

            self.build_device_states(
                self.states[device_id],
                self.get_raw_id(device_id),
            )

    async def refresh_boosted_devices(self):
        # don't let this kick off until we are done with our list
        while not self.discovery_complete and self.running:
            await asyncio.sleep(1)

        if len(self.boosted) > 0:
            self.logger.info(
                f"Refreshing {len(self.boosted)} boosted devices from Blink"
            )
            for device_id in self.boosted:
                if not self.running:
                    break
                self.build_device_states(
                    self.states[device_id],
                    self.get_raw_id(device_id),
                )

    async def refresh_snapshot_all_devices(self):
        self.logger.info(
            f"Requesting snapshots on devices (every {self.snapshot_update_interval} sec)"
        )
        async with timeout(30):
            await self.blink_refresh()

        tasks1 = []
        tasks2 = []
        for device_id in self.devices:
            if self.get_component_type(device_id) == "camera" and self.is_discovered(
                device_id
            ):
                tasks1.append(
                    asyncio.create_task(self.take_snapshot_from_device(device_id))
                )
                tasks2.append(
                    asyncio.create_task(self.refresh_snapshot(device_id, "snapshot"))
                )
        await asyncio.gather(*tasks1)
        await asyncio.gather(*tasks2)

    async def refresh_snapshot(self, device_id, type):
        states = self.states[device_id]

        image = await self.get_snapshot_from_device(device_id)

        # only store and send to MQTT if we got an image AND the image has changed
        if image and (states[type] is None or states[type] != image):
            states[type] = image
            self.publish_device_image(device_id, type)
