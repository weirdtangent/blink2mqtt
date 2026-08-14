# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
"""Tests for clearing/rebuilding HA discovery when the entity layout changes."""

import re
import pytest
from unittest.mock import AsyncMock, MagicMock, call

from blink2mqtt.mixins.helpers import HelpersMixin
from blink2mqtt.mixins.mqtt import MqttMixin
from blink2mqtt.mixins.publish import PublishMixin


class FakeService(HelpersMixin, PublishMixin, MqttMixin):
    def __init__(self, devices=None):
        self.logger = MagicMock()
        self.mqtt_config = {"discovery_prefix": "homeassistant"}
        self.mqtt_helper = MagicMock()
        self.mqtt_helper.service_slug = "blink2mqtt"
        self.mqtt_helper.obj_id = MagicMock(side_effect=lambda dev, e="": re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", f"{dev} {e}".lower())).strip("_"))
        self.mqtt_helper.disc_t = MagicMock(side_effect=lambda kind, did: f"homeassistant/{kind}/blink2mqtt_{did}/config")
        self.devices = {d: {"component": {}} for d in (devices or [])}
        self.states = {d: {"internal": {"discovered": True}} for d in (devices or [])}
        self.dirty = {}
        self.publish_service_state = AsyncMock()

    def upsert_state(self, device_id, **kwargs):
        for section, values in kwargs.items():
            self.states.setdefault(device_id, {}).setdefault(section, {}).update(values)
        return True


def _cleared_topics(svc):
    return [c.args[0] for c in svc.mqtt_helper.safe_publish.call_args_list if c.args[1] == ""]


class TestClearDiscovery:
    @pytest.mark.asyncio
    async def test_delegates_to_the_broker_sweep(self):
        """The device map is empty at connect time, so the topic list must come from the broker."""
        svc = FakeService()
        svc.clear_retained_discovery = AsyncMock()

        await svc.clear_discovery()

        svc.clear_retained_discovery.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clears_topics_the_device_map_never_knew_about(self):
        svc = FakeService()  # no devices loaded yet, exactly as at mqtt_on_connect
        svc.collect_retained_discovery_topics = AsyncMock(
            return_value=[
                "homeassistant/device/blink2mqtt_CAM1/config",
                "homeassistant/device/blink2mqtt_service/config",
            ]
        )

        await svc.clear_discovery()

        assert _cleared_topics(svc) == [
            "homeassistant/device/blink2mqtt_CAM1/config",
            "homeassistant/device/blink2mqtt_service/config",
        ]

    @pytest.mark.asyncio
    async def test_clears_with_empty_payload_retained(self):
        """An empty payload removes the registry entry; None would publish the string "null"."""
        svc = FakeService()
        svc.collect_retained_discovery_topics = AsyncMock(return_value=["homeassistant/device/blink2mqtt_service/config"])

        await svc.clear_discovery()

        for c in svc.mqtt_helper.safe_publish.call_args_list:
            assert c.args[1] == ""
            assert c.kwargs == {"retain": True}

    @pytest.mark.asyncio
    async def test_clears_discovered_flag_or_republish_is_a_no_op(self):
        """publish_device_discovery() early-returns on is_discovered(), so this flag must drop."""
        svc = FakeService(devices=["CAM1"])
        svc.clear_retained_discovery = AsyncMock()
        assert svc.is_discovered("CAM1") is True

        await svc.clear_discovery()

        assert svc.is_discovered("CAM1") is False


class TestRediscoverOrder:
    @pytest.mark.asyncio
    async def test_discovery_precedes_state_per_device(self):
        """publish_device_state() early-returns until discovered, so state cannot go first."""
        svc = FakeService(devices=["CAM1"])
        order = MagicMock()
        svc.publish_service_discovery = AsyncMock()
        svc.publish_device_discovery = AsyncMock(side_effect=lambda d: order.discovery(d))
        svc.publish_device_state = AsyncMock(side_effect=lambda d, **kw: order.state(d))

        await svc.rediscover_all()

        assert order.mock_calls == [call.discovery("CAM1"), call.state("CAM1")]


class TestResetDiscoveryCommand:
    @pytest.mark.asyncio
    async def test_reset_discovery_survives_the_non_numeric_path(self):
        """It must be handled before the int() that every other service command relies on."""
        svc = FakeService()
        svc.reset_discovery = AsyncMock()

        await svc.handle_service_command("reset_discovery", "PRESS")

        svc.reset_discovery.assert_awaited_once()
        svc.logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_numeric_commands_still_work(self):
        svc = FakeService()

        await svc.handle_service_command("refresh_interval", "45")

        assert svc.device_interval == 45
        svc.publish_service_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_numeric_value_for_a_numeric_command_still_rejected(self):
        svc = FakeService()
        svc.reset_discovery = AsyncMock()

        await svc.handle_service_command("refresh_interval", "soon")

        svc.logger.warning.assert_called_once()
        svc.reset_discovery.assert_not_awaited()


class TestSchemaVersion:
    def test_service_declares_a_schema_version(self):
        assert MqttMixin.DISCOVERY_SCHEMA_VERSION >= 1

    def test_version_topic_is_outside_the_command_wildcard(self):
        """`<slug>/service/+/set` must not swallow the version topic."""
        svc = FakeService()

        topic = svc.discovery_schema_version_topic()

        assert topic == "blink2mqtt/service/discovery_schema_version"
        assert not topic.endswith("/set")
        assert len(topic.split("/")) == 3
