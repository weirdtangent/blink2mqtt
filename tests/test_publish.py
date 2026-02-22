# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import json
import pytest
from unittest.mock import MagicMock, patch

from blink2mqtt.mixins.publish import PublishMixin
from blink2mqtt.mixins.helpers import HelpersMixin


class FakePublisher(HelpersMixin, PublishMixin):
    def __init__(self):
        self.service = "blink2mqtt"
        self.service_name = "blink2mqtt service"
        self.qos = 0
        self.config = {"version": "v0.1.0-test"}
        self.logger = MagicMock()
        self.mqtt_helper = MagicMock()
        self.mqtt_helper.safe_publish = MagicMock()
        self.mqtt_helper.service_slug = "blink2mqtt"
        self.mqtt_helper.svc_unique_id = MagicMock(side_effect=lambda e: f"blink2mqtt_{e}")
        self.mqtt_helper.dev_unique_id = MagicMock(side_effect=lambda d, e: f"blink2mqtt_{d}_{e}")
        self.mqtt_helper.device_slug = MagicMock(side_effect=lambda d: f"blink2mqtt_{d}")
        self.mqtt_helper.stat_t = MagicMock(side_effect=lambda *args: "/".join(["blink2mqtt"] + list(args)))
        self.mqtt_helper.avty_t = MagicMock(side_effect=lambda *args: "/".join(["blink2mqtt"] + list(args) + ["availability"]))
        self.mqtt_helper.cmd_t = MagicMock(side_effect=lambda *args: "/".join(["blink2mqtt"] + list(args) + ["set"]))
        self.mqtt_helper.disc_t = MagicMock(side_effect=lambda kind, did: f"homeassistant/{kind}/blink2mqtt_{did}/config")
        self.devices = {}
        self.states = {}


async def _fake_to_thread(fn, *args):
    return fn(*args)


class TestServiceDiscovery:
    @pytest.mark.asyncio
    async def test_publishes_service_discovery(self):
        pub = FakePublisher()

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_service_discovery()

        pub.mqtt_helper.safe_publish.assert_called()
        topic = pub.mqtt_helper.safe_publish.call_args_list[0].args[0]
        payload = json.loads(pub.mqtt_helper.safe_publish.call_args_list[0].args[1])

        assert topic == "homeassistant/device/blink2mqtt_service/config"
        assert "cmps" in payload
        assert len(payload["cmps"]) == 6

    @pytest.mark.asyncio
    async def test_service_discovery_marks_discovered(self):
        pub = FakePublisher()

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_service_discovery()

        assert pub.states["service"]["internal"]["discovered"] is True


class TestServiceAvailability:
    @pytest.mark.asyncio
    async def test_publishes_online(self):
        pub = FakePublisher()

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_service_availability("online")

        assert pub.mqtt_helper.safe_publish.call_args.args[1] == "online"

    @pytest.mark.asyncio
    async def test_publishes_offline(self):
        pub = FakePublisher()

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_service_availability("offline")

        assert pub.mqtt_helper.safe_publish.call_args.args[1] == "offline"


class TestServiceState:
    @pytest.mark.asyncio
    async def test_publishes_all_metrics(self):
        pub = FakePublisher()
        pub.api_calls = 42
        pub.last_call_date = "2026-01-15T10:30:00"
        pub.rate_limited = False
        pub.device_interval = 30
        pub.device_list_interval = 3600
        pub.snapshot_update_interval = 5

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_service_state()

        topics = [c.args[0] for c in pub.mqtt_helper.safe_publish.call_args_list]
        assert any("server" in t for t in topics)
        assert any("api_calls" in t for t in topics)
        assert any("rate_limited" in t for t in topics)

    @pytest.mark.asyncio
    async def test_last_api_call_published(self):
        pub = FakePublisher()
        pub.api_calls = 0
        pub.last_call_date = "2026-01-15T10:30:00"
        pub.rate_limited = False
        pub.device_interval = 30
        pub.device_list_interval = 3600
        pub.snapshot_update_interval = 5

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_service_state()

        for c in pub.mqtt_helper.safe_publish.call_args_list:
            if "last_api_call" in c.args[0]:
                assert "2026" in str(c.args[1])
                break
        else:
            pytest.fail("last_api_call not published")


class TestDeviceDiscovery:
    @pytest.mark.asyncio
    async def test_publishes_when_not_discovered(self):
        pub = FakePublisher()
        pub.devices["BLINK001"] = {
            "component": {
                "device": {"name": "Front Door"},
                "platform": "camera",
            }
        }
        pub.states["BLINK001"] = {}

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_device_discovery("BLINK001")

        pub.mqtt_helper.safe_publish.assert_called_once()
        topic = pub.mqtt_helper.safe_publish.call_args.args[0]
        assert topic == "homeassistant/device/blink2mqtt_BLINK001/config"

    @pytest.mark.asyncio
    async def test_skips_if_already_discovered(self):
        pub = FakePublisher()
        pub.devices["BLINK001"] = {"component": {"device": {"name": "Front Door"}}}
        pub.states["BLINK001"] = {"internal": {"discovered": True}}

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_device_discovery("BLINK001")

        pub.mqtt_helper.safe_publish.assert_not_called()


class TestDeviceAvailability:
    @pytest.mark.asyncio
    async def test_uses_get_device_availability_topic(self):
        pub = FakePublisher()
        pub.devices["BLINK001"] = {"component": {"avty_t": "blink2mqtt/BLINK001/availability"}}
        pub.states["BLINK001"] = {}

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_device_availability("BLINK001", online=True)

        assert pub.mqtt_helper.safe_publish.call_args.args[1] == "online"

    @pytest.mark.asyncio
    async def test_offline(self):
        pub = FakePublisher()
        pub.devices["BLINK001"] = {"component": {"avty_t": "blink2mqtt/BLINK001/availability"}}
        pub.states["BLINK001"] = {}

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_device_availability("BLINK001", online=False)

        assert pub.mqtt_helper.safe_publish.call_args.args[1] == "offline"


class TestDeviceState:
    @pytest.mark.asyncio
    async def test_guards_with_is_discovered(self):
        pub = FakePublisher()
        pub.devices["BLINK001"] = {"component": {"device": {"name": "Front Door"}}}
        pub.states["BLINK001"] = {"sensor": {"battery_status": "OK"}}

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_device_state("BLINK001")

        # Not discovered yet, so should not publish
        pub.mqtt_helper.safe_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_publishes_when_discovered(self):
        pub = FakePublisher()
        pub.devices["BLINK001"] = {"component": {"device": {"name": "Front Door"}}}
        pub.states["BLINK001"] = {
            "internal": {"discovered": True},
            "sensor": {"battery_status": "OK"},
        }

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_device_state("BLINK001")

        topics = [c.args[0] for c in pub.mqtt_helper.safe_publish.call_args_list]
        assert any("battery_status" in t for t in topics)

    @pytest.mark.asyncio
    async def test_list_values_encoded_as_json(self):
        pub = FakePublisher()
        pub.devices["BLINK001"] = {"component": {"device": {"name": "Front Door"}}}
        pub.states["BLINK001"] = {
            "internal": {"discovered": True},
            "sensor": {"items": [1, 2, 3]},
        }

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_device_state("BLINK001")

        for c in pub.mqtt_helper.safe_publish.call_args_list:
            if "items" in c.args[0]:
                assert c.args[1] == json.dumps([1, 2, 3])


class TestDeviceImage:
    @pytest.mark.asyncio
    async def test_publishes_image_from_state(self):
        pub = FakePublisher()
        pub.devices["BLINK001"] = {"component": {"device": {"name": "Front Door"}}}
        pub.states["BLINK001"] = {"snapshot": "base64encodedimage=="}

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_device_image("BLINK001", "snapshot")

        pub.mqtt_helper.safe_publish.assert_called_once()
        assert pub.mqtt_helper.safe_publish.call_args.args[1] == "base64encodedimage=="

    @pytest.mark.asyncio
    async def test_skips_none_image(self):
        pub = FakePublisher()
        pub.devices["BLINK001"] = {"component": {"device": {"name": "Front Door"}}}
        pub.states["BLINK001"] = {"snapshot": None}

        with patch("blink2mqtt.mixins.publish.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = _fake_to_thread
            await pub.publish_device_image("BLINK001", "snapshot")

        pub.mqtt_helper.safe_publish.assert_not_called()
