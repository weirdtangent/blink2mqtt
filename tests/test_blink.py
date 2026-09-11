# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import re
from unittest.mock import AsyncMock, MagicMock

from mqtt_helper import MqttHelper

from blink2mqtt.mixins.blink import BlinkMixin


class FakeBlinkDevice(BlinkMixin):
    def __init__(self):
        self.logger = MagicMock()
        self.mqtt_helper = MagicMock()
        self.mqtt_helper.service_slug = "blink2mqtt"
        self.mqtt_helper.obj_id = MagicMock(side_effect=lambda dev, e="": re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", f"{dev} {e}".lower())).strip("_"))
        # the real rewrite -- this is the step HA's entity_ids depend on, so it must not be a stub
        self.mqtt_helper.apply_default_entity_ids = MagicMock(side_effect=MqttHelper("blink2mqtt").apply_default_entity_ids)
        self.devices = {}
        self.states = {}


class TestClassifyDevice:
    def test_sync_module_returns_switch(self):
        blink = FakeBlinkDevice()
        device = {"device_type": "sync_module", "device_name": "My Sync"}

        result = blink.classify_device(device)

        assert result == "switch"

    def test_owl_returns_camera(self):
        blink = FakeBlinkDevice()
        device = {"device_type": "owl", "device_name": "Mini Camera"}

        result = blink.classify_device(device)

        assert result == "camera"

    def test_catalina_returns_camera(self):
        blink = FakeBlinkDevice()
        device = {"device_type": "catalina", "device_name": "Outdoor Camera"}

        result = blink.classify_device(device)

        assert result == "camera"

    def test_no_device_type_returns_none(self):
        blink = FakeBlinkDevice()
        device = {"device_name": "Unknown Device"}

        result = blink.classify_device(device)

        assert result is None
        blink.logger.warning.assert_called_once()

    def test_none_device_type_returns_none(self):
        blink = FakeBlinkDevice()
        device = {"device_type": None, "device_name": "Ghost Device"}

        result = blink.classify_device(device)

        assert result is None
        blink.logger.warning.assert_called_once()


class TestRefreshDeviceListDiscoveryNotice:
    """The 'first-time device setup and discovery is done' line was emitted on
    every periodic refresh, not just the first one, which made every hourly
    refresh read like a fresh startup in the logs.
    """

    def _make_fake(self):
        fake = FakeBlinkDevice()
        fake.discovery_complete = False
        fake.device_list_interval = 3600
        fake.get_cameras = AsyncMock(return_value={})
        fake.get_sync_modules = AsyncMock(return_value={})
        fake.publish_service_state = AsyncMock()
        fake.publish_device_availability = AsyncMock()
        fake.build_component = AsyncMock(return_value="")
        return fake

    def _messages(self, fake):
        return [call[0][0] for call in fake.logger.info.call_args_list]

    async def test_notice_is_logged_on_first_pass(self):
        fake = self._make_fake()

        await fake.refresh_device_list()

        assert "first-time device setup and discovery is done" in self._messages(fake)
        assert fake.discovery_complete is True

    async def test_notice_is_not_repeated_on_later_passes(self):
        fake = self._make_fake()

        await fake.refresh_device_list()
        fake.logger.info.reset_mock()
        await fake.refresh_device_list()

        assert "first-time device setup and discovery is done" not in self._messages(fake)
        # the periodic refresh line is still logged, so the pass is not silent
        assert any("refreshing device list from Blink" in message for message in self._messages(fake))
