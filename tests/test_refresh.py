# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from blink2mqtt.mixins.refresh import RefreshMixin
from blink2mqtt.mixins.helpers import HelpersMixin


class FakeRefresher(HelpersMixin, RefreshMixin):
    def __init__(self):
        self.logger = MagicMock()
        self.running = True
        self.device_interval = 30
        self.snapshot_update_interval = 5
        self.devices = {}
        self.states = {}
        self.blink_cameras = {}
        self.blink_sync_modules = {}

    async def blink_refresh(self):
        pass

    async def get_cameras(self):
        return self.blink_cameras

    async def get_sync_modules(self):
        return self.blink_sync_modules

    async def build_camera_states(self, device_id, device):
        pass

    async def build_sync_module_states(self, device_id, sync_module):
        pass

    async def publish_device_state(self, device_id):
        pass

    async def take_snapshot_from_device(self, device_id):
        pass

    async def get_snapshot_from_device(self, device_id):
        return None

    async def publish_device_image(self, device_id, type):
        pass


class TestRefreshAllDevices:
    @pytest.mark.asyncio
    async def test_handles_cameras_and_sync_modules(self):
        r = FakeRefresher()
        r.blink_cameras = {"CAM001": {"name": "Front"}}
        r.blink_sync_modules = {"SYNC001": {"name": "Hub"}}
        r.blink_refresh = AsyncMock()
        r.get_cameras = AsyncMock(return_value=r.blink_cameras)
        r.get_sync_modules = AsyncMock(return_value=r.blink_sync_modules)
        r.build_camera_states = AsyncMock()
        r.build_sync_module_states = AsyncMock()
        r.publish_device_state = AsyncMock()

        await r.refresh_all_devices()

        r.blink_refresh.assert_called_once()
        r.build_camera_states.assert_called_once()
        r.build_sync_module_states.assert_called_once()
        assert r.publish_device_state.call_count == 2

    @pytest.mark.asyncio
    async def test_gather_pattern(self):
        r = FakeRefresher()
        r.blink_cameras = {"CAM001": {}, "CAM002": {}}
        r.blink_sync_modules = {}
        r.blink_refresh = AsyncMock()
        r.get_cameras = AsyncMock(return_value=r.blink_cameras)
        r.get_sync_modules = AsyncMock(return_value=r.blink_sync_modules)
        r.build_camera_states = AsyncMock()
        r.publish_device_state = AsyncMock()

        await r.refresh_all_devices()

        assert r.build_camera_states.call_count == 2


class TestRefreshSnapshot:
    @pytest.mark.asyncio
    async def test_new_image_updates_state(self):
        r = FakeRefresher()
        r.states = {"CAM001": {}}
        r.get_snapshot_from_device = AsyncMock(return_value="new_image_b64")
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        await r.refresh_snapshot("CAM001", "snapshot")

        assert r.states["CAM001"]["snapshot"] == "new_image_b64"
        r.publish_device_state.assert_called_once()
        r.publish_device_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_unchanged_image_not_published(self):
        r = FakeRefresher()
        r.states = {"CAM001": {"snapshot": "same_image"}}
        r.get_snapshot_from_device = AsyncMock(return_value="same_image")
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        await r.refresh_snapshot("CAM001", "snapshot")

        r.publish_device_state.assert_not_called()
        r.publish_device_image.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_image_not_published(self):
        r = FakeRefresher()
        r.states = {"CAM001": {}}
        r.get_snapshot_from_device = AsyncMock(return_value=None)
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        await r.refresh_snapshot("CAM001", "snapshot")

        r.publish_device_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_image_sets_datetime(self):
        r = FakeRefresher()
        r.states = {"CAM001": {}}
        r.get_snapshot_from_device = AsyncMock(return_value="new_image")
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        await r.refresh_snapshot("CAM001", "snapshot")

        # upsert_state should have set last_event_time
        sensor = r.states["CAM001"].get("sensor", {})
        assert sensor.get("last_event") == "Timed snapshot"
        assert "T" in sensor.get("last_event_time", "")


class TestRefreshSnapshotAllDevices:
    @pytest.mark.asyncio
    async def test_two_phase_gather_with_sleep(self):
        r = FakeRefresher()
        r.blink_cameras = {"CAM001": {}, "CAM002": {}}
        r.states = {"CAM001": {}, "CAM002": {}}
        r.take_snapshot_from_device = AsyncMock()
        r.blink_refresh = AsyncMock()
        r.get_snapshot_from_device = AsyncMock(return_value="img")
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        with patch("blink2mqtt.mixins.refresh.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await r.refresh_snapshot_all_devices()

        # Phase 1: take snapshots, Phase 2: refresh snapshots
        assert r.take_snapshot_from_device.call_count == 2
        mock_sleep.assert_called_once_with(3)
        r.blink_refresh.assert_called_once()
