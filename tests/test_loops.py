# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from blink2mqtt.mixins.loops import LoopsMixin
from blink2mqtt.mixins.helpers import HelpersMixin


class FakeLooper(HelpersMixin, LoopsMixin):
    def __init__(self):
        self.logger = MagicMock()
        self.running = True
        self.device_interval = 1
        self.device_list_interval = 1
        self.snapshot_update_interval = 1

    async def refresh_all_devices(self):
        pass

    async def refresh_device_list(self):
        pass

    async def refresh_snapshot_all_devices(self):
        pass

    async def collect_all_blink_events(self):
        pass

    async def process_events(self):
        pass

    async def connect(self):
        pass

    def mark_ready(self):
        pass

    def heartbeat_ready(self):
        pass


class TestDeviceLoop:
    @pytest.mark.asyncio
    async def test_sleep_first_then_refresh(self):
        looper = FakeLooper()
        call_order = []

        async def mock_sleep(seconds):
            call_order.append("sleep")
            looper.running = False

        async def mock_refresh():
            call_order.append("refresh")

        looper.refresh_all_devices = mock_refresh

        with patch("blink2mqtt.mixins.loops.asyncio.sleep", side_effect=mock_sleep):
            await looper.device_loop()

        # blink2mqtt sleeps first, then refreshes (no running check between sleep and refresh)
        assert call_order == ["sleep", "refresh"]

    @pytest.mark.asyncio
    async def test_handles_cancelled_error(self):
        looper = FakeLooper()

        with patch("blink2mqtt.mixins.loops.asyncio.sleep", side_effect=asyncio.CancelledError):
            await looper.device_loop()

        looper.logger.debug.assert_called()


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_sleep_first_then_heartbeat(self):
        looper = FakeLooper()
        heartbeat_called = False

        def mock_heartbeat():
            nonlocal heartbeat_called
            heartbeat_called = True
            looper.running = False

        looper.heartbeat_ready = mock_heartbeat

        async def mock_sleep(seconds):
            pass

        call_count = 0

        async def mock_sleep_then_stop(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                looper.running = False

        with patch("blink2mqtt.mixins.loops.asyncio.sleep", side_effect=mock_sleep_then_stop):
            await looper.heartbeat()

        assert heartbeat_called

    @pytest.mark.asyncio
    async def test_handles_cancelled_error(self):
        looper = FakeLooper()

        with patch("blink2mqtt.mixins.loops.asyncio.sleep", side_effect=asyncio.CancelledError):
            await looper.heartbeat()

        looper.logger.debug.assert_called()


class TestMainLoop:
    @pytest.mark.asyncio
    async def test_initialization_sequence(self):
        looper = FakeLooper()
        call_order = []

        looper.connect = AsyncMock(side_effect=lambda: call_order.append("connect"))
        looper.refresh_device_list = AsyncMock(side_effect=lambda: call_order.append("refresh_device_list"))
        looper.refresh_snapshot_all_devices = AsyncMock(side_effect=lambda: call_order.append("refresh_snapshot"))
        looper.handle_signal = MagicMock()

        with (
            patch("blink2mqtt.mixins.loops.signal.signal"),
            patch("blink2mqtt.mixins.loops.asyncio.create_task", side_effect=lambda coro, **kw: asyncio.ensure_future(coro)),
            patch("blink2mqtt.mixins.loops.asyncio.gather", new_callable=AsyncMock),
        ):
            await looper.main_loop()

        assert call_order == ["connect", "refresh_device_list", "refresh_snapshot"]

    @pytest.mark.asyncio
    async def test_creates_4_tasks(self):
        looper = FakeLooper()
        looper.connect = AsyncMock()
        looper.refresh_device_list = AsyncMock()
        looper.refresh_snapshot_all_devices = AsyncMock()
        looper.handle_signal = MagicMock()
        created_tasks = []

        def mock_create_task(coro, **kwargs):
            created_tasks.append(kwargs.get("name", "unknown"))
            task = asyncio.ensure_future(coro)
            task.cancel()
            return task

        with (
            patch("blink2mqtt.mixins.loops.signal.signal"),
            patch("blink2mqtt.mixins.loops.asyncio.create_task", side_effect=mock_create_task),
            patch("blink2mqtt.mixins.loops.asyncio.gather", new_callable=AsyncMock),
        ):
            await looper.main_loop()

        assert len(created_tasks) == 4
        assert "device_list_loop" in created_tasks
        assert "device_loop" in created_tasks
        assert "collect_snapshots_loop" in created_tasks
        assert "heartbeat" in created_tasks
