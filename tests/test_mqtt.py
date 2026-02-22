# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from blink2mqtt.mixins.mqtt import MqttMixin


class FakeMqtt(MqttMixin):
    def __init__(self):
        self.logger = MagicMock()
        self.mqtt_config = {"discovery_prefix": "homeassistant"}
        self.mqtt_helper = MagicMock()
        self.mqtt_helper.service_slug = "blink2mqtt"
        self.devices = {}
        self.states = {}

        # Async methods that may be called by mqtt_on_message routing
        self.handle_homeassistant_message = AsyncMock()
        self.handle_service_command = AsyncMock()
        self.handle_device_topic = AsyncMock()


def _make_msg(topic, payload):
    """Create a fake MQTTMessage with the given topic and payload."""
    msg = MagicMock()
    msg.topic = topic
    if isinstance(payload, dict):
        msg.payload = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        msg.payload = payload.encode("utf-8")
    else:
        msg.payload = payload
    return msg


class TestMqttSubscriptionTopics:
    def test_returns_expected_topics(self):
        mqtt = FakeMqtt()
        topics = mqtt.mqtt_subscription_topics()

        assert "homeassistant/status" in topics
        assert "blink2mqtt/service/+/set" in topics
        assert "blink2mqtt/service/+/command" in topics
        assert "blink2mqtt/+/switch/+/set" in topics

    def test_returns_list(self):
        mqtt = FakeMqtt()
        topics = mqtt.mqtt_subscription_topics()
        assert isinstance(topics, list)
        assert len(topics) == 4


class TestMqttOnMessage:
    @pytest.mark.asyncio
    async def test_ha_online_routes_to_homeassistant_handler(self):
        mqtt = FakeMqtt()
        msg = _make_msg("homeassistant/status", "online")

        await MqttMixin.mqtt_on_message(mqtt, None, None, msg)

        mqtt.handle_homeassistant_message.assert_called_once_with("online")

    @pytest.mark.asyncio
    async def test_service_topic_routes_to_service_handler(self):
        mqtt = FakeMqtt()
        # "60" is valid JSON and json.loads("60") returns int 60
        msg = _make_msg("blink2mqtt/service/refresh_interval/set", "60")

        await MqttMixin.mqtt_on_message(mqtt, None, None, msg)

        mqtt.handle_service_command.assert_called_once_with("refresh_interval", 60)

    @pytest.mark.asyncio
    async def test_device_topic_routes_to_device_handler(self):
        mqtt = FakeMqtt()
        msg = _make_msg("blink2mqtt/blink2mqtt_SERIAL123/switch/motion_detection/set", "ON")

        await MqttMixin.mqtt_on_message(mqtt, None, None, msg)

        mqtt.handle_device_topic.assert_called_once()
        args = mqtt.handle_device_topic.call_args[0]
        assert args[0] == ["blink2mqtt", "blink2mqtt_SERIAL123", "switch", "motion_detection", "set"]
        assert args[1] == "ON"


class TestParseDeviceTopic:
    def test_valid_topic_parses_correctly(self):
        mqtt = FakeMqtt()
        components = ["blink2mqtt", "blink2mqtt_SERIAL123", "switch", "motion_detection", "set"]

        result = mqtt._parse_device_topic(components)

        assert result == ["blink2mqtt", "SERIAL123", "motion_detection"]

    def test_non_set_topic_returns_none(self):
        mqtt = FakeMqtt()
        components = ["blink2mqtt", "blink2mqtt_SERIAL123", "switch", "motion_detection", "get"]

        result = mqtt._parse_device_topic(components)

        assert result is None

    def test_malformed_topic_returns_none(self):
        mqtt = FakeMqtt()
        components = ["set"]

        result = mqtt._parse_device_topic(components)

        assert result is None


class TestHandleHomeassistantMessage:
    @pytest.mark.asyncio
    async def test_online_calls_rediscover_all(self):
        mqtt = FakeMqtt()
        mqtt.rediscover_all = AsyncMock()

        # Call the real method on the class, not the mock
        await MqttMixin.handle_homeassistant_message(mqtt, "online")

        mqtt.rediscover_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_offline_does_not_call_rediscover(self):
        mqtt = FakeMqtt()
        mqtt.rediscover_all = AsyncMock()

        await MqttMixin.handle_homeassistant_message(mqtt, "offline")

        mqtt.rediscover_all.assert_not_called()
