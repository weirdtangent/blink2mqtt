# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from unittest.mock import MagicMock

from blink2mqtt.mixins.blink import BlinkMixin


class FakeBlinkDevice(BlinkMixin):
    def __init__(self):
        self.logger = MagicMock()
        self.mqtt_helper = MagicMock()
        self.mqtt_helper.service_slug = "blink2mqtt"
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
