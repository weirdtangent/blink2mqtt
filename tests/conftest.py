# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import pytest


@pytest.fixture
def sample_blink_config():
    return {
        "mqtt": {
            "host": "10.10.10.1",
            "port": 1883,
            "qos": 0,
            "protocol_version": "5",
            "username": "mqtt_user",
            "password": "mqtt_pass",
            "tls_enabled": False,
            "prefix": "blink2mqtt",
            "discovery_prefix": "homeassistant",
        },
        "blink": {
            "username": "blink_user",
            "password": "blink_pass",
            "device_interval": 30,
            "device_list_interval": 3600,
            "snapshot_update_interval": 5,
        },
    }
