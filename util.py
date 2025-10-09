# This software is licensed under the MIT License, which allows you to use,
# copy, modify, merge, publish, distribute, and sell copies of the software,
# with the requirement to include the original copyright notice and this
# permission notice in all copies or substantial portions of the software.
#
# The software is provided 'as is', without any warranty.

import os
import logging
import yaml

# Helper functions and callbacks
def read_file(file_name):
    """Read a text file safely and strip trailing newlines only."""
    try:
        with open(file_name, 'r', encoding='utf-8') as file:
            return file.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_name}")

def read_version():
    """Return version string from VERSION file (current or parent dir)."""
    for path in ("./VERSION", "../VERSION"):
        if os.path.isfile(path):
            return read_file(path)
    raise FileNotFoundError("VERSION file not found in current or parent directory.")

def _defaults():
    """Default config schema with types and defaults."""
    return {
        "mqtt": {
            "host": "localhost",
            "port": 1883,
            "username": "",
            "password": "",
            "qos": 0,
            "prefix": "blink2mqtt",
            "reconnect_delay": 30,
            "home_assistant": True,
            "discovery_prefix": "homeassistant",
            "tls_enabled": False,
            "tls_ca_cert": None,
            "tls_cert": None,
            "tls_key": None,
        },
        "blink": {
            "username": "admin",
            "password": "",
            "device_rescan_interval": 3600,
            "device_update_interval": 900,
            "snapshot_update_interval": 300,
        },
        "timezone": "UTC",
        "hide_ts": False,
        "debug": False,
    }

def load_config(config_path="/config/config.yaml"):
    """Load configuration from YAML or environment, normalize, and fill defaults."""
    logger = logging.getLogger(__name__)

    # Allow user to pass either directory or file
    if os.path.isdir(config_path):
        config_path = os.path.join(config_path.rstrip("/"), "config.yaml")

    config = None
    config_from = "env"

    # Try YAML file first
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            config_from = "file"
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as err:
            logger.warning(f"Failed to load YAML config ({err}), falling back to environment")

    # Fallback to env if YAML missing or invalid
    if not config:
        config = {
            "mqtt": {
                "host": os.getenv("MQTT_HOST", "localhost"),
                "port": int(os.getenv("MQTT_PORT", 1883)),
                "username": os.getenv("MQTT_USERNAME", ""),
                "password": os.getenv("MQTT_PASSWORD", ""),
                "qos": int(os.getenv("MQTT_QOS", 0)),
                "prefix": os.getenv("MQTT_PREFIX", "blink2mqtt"),
                "reconnect_delay": int(os.getenv("MQTT_RECONNECT_DELAY", 30)),
                "home_assistant": os.getenv("MQTT_HOMEASSISTANT", "true").lower() == "true",
                "discovery_prefix": os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"),
                "tls_enabled": os.getenv("MQTT_TLS_ENABLED", "false").lower() == "true",
                "tls_ca_cert": os.getenv("MQTT_TLS_CA_CERT"),
                "tls_cert": os.getenv("MQTT_TLS_CERT"),
                "tls_key": os.getenv("MQTT_TLS_KEY"),
            },
            "blink": {
                "username": os.getenv("BLINK_USERNAME", "admin"),
                "password": os.getenv("BLINK_PASSWORD", ""),
                "device_rescan_interval": int(os.getenv("DEVICE_RESCAN_INTERVAL", 3600)),
                "device_update_interval": int(os.getenv("DEVICE_UPDATE_INTERVAL", 900)),
                "snapshot_update_interval": int(os.getenv("SNAPSHOT_UPDATE_INTERVAL", 300)),
            },
            "timezone": os.getenv("TZ", "UTC"),
            "hide_ts": os.getenv("HIDE_TS", "false").lower() == "true",
            "debug": os.getenv("DEBUG", "false").lower() == "true",
        }

    # Apply defaults recursively
    defaults = _defaults()

    def fill_defaults(defaults_dict, target_dict):
        for key, default_value in defaults_dict.items():
            if isinstance(default_value, dict):
                target_dict.setdefault(key, {})
                fill_defaults(default_value, target_dict[key])
            else:
                if key not in target_dict:
                    target_dict[key] = default_value
                    logger.debug(f"Default applied: {key} = {default_value}")

    fill_defaults(defaults, config)

    config["config_path"] = os.path.dirname(config_path)
    config["config_from"] = config_from
    return config