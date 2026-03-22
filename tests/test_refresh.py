# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from blink2mqtt.mixins.refresh import RefreshMixin
from blink2mqtt.mixins.helpers import HelpersMixin


class FakeRefresher(HelpersMixin, RefreshMixin):
    def __init__(self):
        self.logger = MagicMock()
        self.loop = MagicMock()
        self.running = True
        self.device_interval = 30
        self.snapshot_interval_wired_minutes = 5
        self.snapshot_interval_battery_hours = 0
        self.devices = {}
        self.states = {}
        self.dirty = {}
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
        r.blink_cameras = {"WIRED_CAMERA": {"name": "Front"}}
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
        r.blink_cameras = {"WIRED_CAMERA": {}, "BATTERY_CAMERA": {}}
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
        r.states = {"WIRED_CAMERA": {}}
        r.get_snapshot_from_device = AsyncMock(return_value="new_image_b64")
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        await r.refresh_snapshot("WIRED_CAMERA", "snapshot")

        assert r.states["WIRED_CAMERA"]["snapshot"] == "new_image_b64"
        r.publish_device_state.assert_called_once()
        r.publish_device_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_unchanged_image_not_published(self):
        r = FakeRefresher()
        r.states = {"WIRED_CAMERA": {"snapshot": "same_image"}}
        r.get_snapshot_from_device = AsyncMock(return_value="same_image")
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        await r.refresh_snapshot("WIRED_CAMERA", "snapshot")

        r.publish_device_state.assert_not_called()
        r.publish_device_image.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_image_not_published(self):
        r = FakeRefresher()
        r.states = {"WIRED_CAMERA": {}}
        r.get_snapshot_from_device = AsyncMock(return_value=None)
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        await r.refresh_snapshot("WIRED_CAMERA", "snapshot")

        r.publish_device_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_image_sets_datetime(self):
        r = FakeRefresher()
        r.states = {"WIRED_CAMERA": {}}
        r.get_snapshot_from_device = AsyncMock(return_value="new_image")
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        await r.refresh_snapshot("WIRED_CAMERA", "snapshot")

        # upsert_state should have set last_event_time
        sensor = r.states["WIRED_CAMERA"].get("sensor", {})
        assert sensor.get("last_event") == "Timed snapshot"
        assert "T" in sensor.get("last_event_time", "")


class TestRefreshSnapshotAllDevices:
    @pytest.mark.asyncio
    async def test_two_phase_gather_with_sleep(self):
        r = FakeRefresher()
        r.blink_cameras = {"WIRED_CAMERA": {}, "BATTERY_CAMERA": {}}
        r.states = {"WIRED_CAMERA": {}, "BATTERY_CAMERA": {}}
        r.take_snapshot_from_device = AsyncMock()
        r.blink_refresh = AsyncMock()
        r.get_snapshot_from_device = AsyncMock(return_value="img")
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        mock_sleep = AsyncMock()

        async def fake_sleep(seconds):
            await mock_sleep(seconds)

        with patch("blink2mqtt.mixins.refresh.asyncio.sleep", side_effect=fake_sleep):
            await r.refresh_snapshot_all_devices()

        # Phase 1: take snapshots, Phase 2: refresh snapshots
        assert r.take_snapshot_from_device.call_count == 2
        mock_sleep.assert_called_once_with(3)
        r.blink_refresh.assert_called_once()
        assert "last_snapshot" in r.states["WIRED_CAMERA"]["internal"]
        assert "last_snapshot" in r.states["BATTERY_CAMERA"]["internal"]

    @pytest.mark.asyncio
    async def test_refresh_snapshot_devices_limits_to_requested_ids(self):
        r = FakeRefresher()
        r.blink_cameras = {"WIRED_CAMERA": {}, "BATTERY_CAMERA": {}}
        r.states = {"WIRED_CAMERA": {}, "BATTERY_CAMERA": {}}
        r.take_snapshot_from_device = AsyncMock()
        r.blink_refresh = AsyncMock()
        r.get_snapshot_from_device = AsyncMock(return_value="img")
        r.publish_device_state = AsyncMock()
        r.publish_device_image = AsyncMock()

        async def fake_sleep(seconds):
            return None

        with patch("blink2mqtt.mixins.refresh.asyncio.sleep", side_effect=fake_sleep):
            await r.refresh_snapshot_devices(["BATTERY_CAMERA"])

        r.take_snapshot_from_device.assert_called_once_with("BATTERY_CAMERA")
        assert "last_snapshot" in r.states["BATTERY_CAMERA"]["internal"]
        assert "internal" not in r.states["WIRED_CAMERA"]
