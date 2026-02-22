# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from blink2mqtt.base import Base


class FakeBase(Base):
    """Minimal subclass so super() works in Base.__aenter__/__aexit__."""

    pass


class TestContextManager:
    @pytest.mark.asyncio
    async def test_aenter_calls_mqttc_create_and_sets_running(self):
        obj = object.__new__(FakeBase)
        obj.logger = MagicMock()
        obj.mqttc_create = AsyncMock()
        obj.running = False

        await Base.__aenter__(obj)

        obj.mqttc_create.assert_called_once()
        assert obj.running is True

    @pytest.mark.asyncio
    async def test_aexit_closes_session_and_disconnects(self):
        obj = object.__new__(FakeBase)
        obj.logger = MagicMock()
        obj.running = True
        obj.session = MagicMock()
        obj.session.closed = False
        obj.session.close = AsyncMock()
        obj.publish_service_availability = AsyncMock()
        obj.mqttc = MagicMock()
        obj.mqttc.is_connected.return_value = True
        obj.mqttc.loop_stop = MagicMock()
        obj.mqttc.disconnect = MagicMock()

        # Mock the running loop
        with patch("blink2mqtt.base.asyncio.get_running_loop") as mock_loop:
            loop = MagicMock()
            loop.is_running.return_value = True
            loop.create_task = MagicMock()
            mock_loop.return_value = loop

            await Base.__aexit__(obj, None, None, None)

        assert obj.running is False
        obj.publish_service_availability.assert_called_once_with("offline")
        obj.mqttc.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_aexit_handles_no_session(self):
        obj = object.__new__(FakeBase)
        obj.logger = MagicMock()
        obj.running = True
        obj.session = None
        obj.publish_service_availability = AsyncMock()
        obj.mqttc = MagicMock()
        obj.mqttc.is_connected.return_value = False
        obj.mqttc.loop_stop = MagicMock()

        await Base.__aexit__(obj, None, None, None)

        assert obj.running is False
