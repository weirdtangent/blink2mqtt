# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import os
import pytest
from unittest.mock import MagicMock

from blink2mqtt.mixins.helpers import ConfigError, HelpersMixin


class FakeHelpers(HelpersMixin):
    def __init__(self):
        self.logger = MagicMock()
        self.running = True


class TestLoadConfigFromFile:
    def test_loads_valid_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
mqtt:
  host: 10.10.10.1
  port: 1883
  username: mqtt
  password: secret
  prefix: blink2mqtt

blink:
  username: blink_user
  password: blink_pass
  device_update_interval: 30
  device_rescan_interval: 3600
  snapshot_update_interval: 5
""")
        version_file = tmp_path / "VERSION"
        version_file.write_text("v0.1.0")

        helpers = FakeHelpers()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            config = helpers.load_config(str(tmp_path))
        finally:
            os.chdir(old_cwd)

        assert config["mqtt"]["host"] == "10.10.10.1"
        assert config["mqtt"]["port"] == 1883
        assert config["mqtt"]["username"] == "mqtt"
        assert config["mqtt"]["prefix"] == "blink2mqtt"
        assert config["blink"]["username"] == "blink_user"
        assert config["blink"]["device_interval"] == 30
        assert config["blink"]["device_list_interval"] == 3600
        assert config["blink"]["snapshot_update_interval"] == 5
        assert config["config_from"] == "file"


class TestLoadConfigDefaults:
    def test_defaults_when_no_file(self, tmp_path, monkeypatch):
        """When no config file exists, env vars and defaults are used."""
        version_file = tmp_path / "VERSION"
        version_file.write_text("v0.1.0")

        monkeypatch.setenv("BLINK_USERNAME", "env_blink_user")

        helpers = FakeHelpers()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            config = helpers.load_config(str(tmp_path))
        finally:
            os.chdir(old_cwd)

        assert config["mqtt"]["host"] == "localhost"
        assert config["mqtt"]["port"] == 1883
        assert config["mqtt"]["qos"] == 0
        assert config["mqtt"]["prefix"] == "blink2mqtt"
        assert config["mqtt"]["protocol_version"] == "5"
        assert config["mqtt"]["discovery_prefix"] == "homeassistant"
        assert config["blink"]["username"] == "env_blink_user"
        assert config["config_from"] == "env"


class TestLoadConfigValidation:
    def test_missing_blink_username_defaults_to_admin(self, tmp_path, monkeypatch):
        """When blink.username is omitted and BLINK_USERNAME env is unset, it defaults to 'admin'."""
        monkeypatch.delenv("BLINK_USERNAME", raising=False)

        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
mqtt:
  host: localhost
blink:
  password: secret
""")
        version_file = tmp_path / "VERSION"
        version_file.write_text("v0.1.0")

        helpers = FakeHelpers()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            config = helpers.load_config(str(tmp_path))
        finally:
            os.chdir(old_cwd)

        assert config["blink"]["username"] == "admin"

    def test_config_error_is_importable(self):
        """ConfigError is a ValueError subclass used for config validation."""
        assert issubclass(ConfigError, ValueError)


class TestLoadConfigVersion:
    def test_app_version_env_overrides_file(self, tmp_path, monkeypatch):
        version_file = tmp_path / "VERSION"
        version_file.write_text("v0.1.0")
        monkeypatch.setenv("APP_VERSION", "v9.9.9")
        monkeypatch.setenv("BLINK_USERNAME", "user")

        helpers = FakeHelpers()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            config = helpers.load_config(str(tmp_path))
        finally:
            os.chdir(old_cwd)

        assert config["version"] == "v9.9.9"

    def test_dev_tier_appends_suffix(self, tmp_path, monkeypatch):
        version_file = tmp_path / "VERSION"
        version_file.write_text("v0.1.0")
        monkeypatch.setenv("APP_TIER", "dev")
        monkeypatch.setenv("BLINK_USERNAME", "user")

        helpers = FakeHelpers()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            config = helpers.load_config(str(tmp_path))
        finally:
            os.chdir(old_cwd)

        assert config["version"] == "v0.1.0:DEV"


class TestReadFile:
    def test_reads_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("  hello world  \n")

        helpers = FakeHelpers()
        assert helpers.read_file(str(f)) == "hello world"

    def test_missing_file_raises(self):
        helpers = FakeHelpers()
        with pytest.raises(FileNotFoundError):
            helpers.read_file("/nonexistent/file.txt")


class TestHandleSignal:
    def test_sets_running_false(self):
        helpers = FakeHelpers()
        assert helpers.running is True

        helpers.handle_signal(2, None)  # SIGINT = 2

        assert helpers.running is False
        helpers.logger.warning.assert_called_once()


class TestUpsertDevice:
    def test_upsert_device_creates_new_entry(self):
        helpers = FakeHelpers()
        helpers.devices = {}
        helpers.states = {}

        changed = helpers.upsert_device("DEV001", component={"platform": "switch", "name": "Test"})
        assert changed is True
        assert "DEV001" in helpers.devices
        assert helpers.devices["DEV001"]["component"]["platform"] == "switch"

    def test_upsert_device_same_data_returns_false(self):
        helpers = FakeHelpers()
        helpers.devices = {}
        helpers.states = {}

        helpers.upsert_device("DEV001", component={"platform": "switch", "name": "Test"})
        changed = helpers.upsert_device("DEV001", component={"platform": "switch", "name": "Test"})
        assert changed is False

    def test_upsert_state_merges_nested_dicts(self):
        helpers = FakeHelpers()
        helpers.devices = {}
        helpers.states = {}

        helpers.upsert_state("DEV001", sensor={"temperature": 72})
        helpers.upsert_state("DEV001", sensor={"battery": "OK"})

        assert helpers.states["DEV001"]["sensor"]["temperature"] == 72
        assert helpers.states["DEV001"]["sensor"]["battery"] == "OK"


class TestSnapshotIntervalMigration:
    def test_large_interval_divided_by_sixty(self, tmp_path, monkeypatch):
        """snapshot_update_interval > 60 gets divided by 60 (legacy seconds -> minutes migration)."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
mqtt:
  host: localhost
blink:
  username: blink_user
  snapshot_update_interval: 300
""")
        version_file = tmp_path / "VERSION"
        version_file.write_text("v0.1.0")

        helpers = FakeHelpers()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            config = helpers.load_config(str(tmp_path))
        finally:
            os.chdir(old_cwd)

        assert config["blink"]["snapshot_update_interval"] == 5

    def test_small_interval_unchanged(self, tmp_path, monkeypatch):
        """snapshot_update_interval <= 60 is kept as-is."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
mqtt:
  host: localhost
blink:
  username: blink_user
  snapshot_update_interval: 10
""")
        version_file = tmp_path / "VERSION"
        version_file.write_text("v0.1.0")

        helpers = FakeHelpers()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            config = helpers.load_config(str(tmp_path))
        finally:
            os.chdir(old_cwd)

        assert config["blink"]["snapshot_update_interval"] == 10
