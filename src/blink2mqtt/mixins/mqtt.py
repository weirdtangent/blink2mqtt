# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
from datetime import datetime, timedelta
import json
import paho.mqtt.client as mqtt
from paho.mqtt.client import Client, MQTTMessageInfo, MQTTMessage, PayloadType
from paho.mqtt.enums import LogLevel
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode
from paho.mqtt.enums import CallbackAPIVersion
import ssl
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class MqttMixin:
    def mqttc_create(self: Blink2Mqtt) -> None:
        self.mqttc = mqtt.Client(
            client_id=self.client_id,
            callback_api_version=CallbackAPIVersion.VERSION2,
            reconnect_on_failure=False,
            protocol=mqtt.MQTTv5,
        )

        if self.mqtt_config.get("tls_enabled"):
            self.mqttc.tls_set(
                ca_certs=self.mqtt_config.get("tls_ca_cert"),
                certfile=self.mqtt_config.get("tls_cert"),
                keyfile=self.mqtt_config.get("tls_key"),
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS,
            )
        if self.mqtt_config.get("username") or self.mqtt_config.get("password"):
            self.mqttc.username_pw_set(
                username=self.mqtt_config.get("username") or None,
                password=self.mqtt_config.get("password") or None,
            )

        # to get around that these _v2 attributes don't exist until run-time
        mqttc_any = self.mqttc  # type: Any
        mqttc_any.on_connect_v2 = self.mqtt_on_connect
        mqttc_any.on_disconnect_v2 = self.mqtt_on_disconnect
        mqttc_any.on_message_v2 = self.mqtt_on_message
        mqttc_any.on_subscribe_v2 = self.mqtt_on_subscribe
        mqttc_any.on_log_v2 = self.mqtt_on_log

        # Define a "last will" message (LWT):
        self.mqttc.will_set(self.mqtt_helper.svc_t("status"), "offline", qos=1, retain=True)

        try:
            host = self.mqtt_config["host"]
            port = self.mqtt_config["port"]
            self.logger.info(f"Connecting to MQTT broker at {host}:{port} as client id: {self.client_id}")

            props = Properties(PacketTypes.CONNECT)
            props.SessionExpiryInterval = 0

            self.mqttc.connect(host=host, port=port, keepalive=60, properties=props)
            self.logger.info(f"Successful connection to {host} MQTT broker")

            self.mqtt_connect_time = datetime.now()
            self.mqttc.loop_start()
        except ConnectionError as error:
            self.logger.error(f"Failed to connect to MQTT host {host}: {error}")
            self.running = False
            raise SystemExit(1)
        except Exception as error:
            self.logger.error(f"Network problem trying to connect to MQTT host {host}: {error}")
            self.running = False
            raise SystemExit(1)

    def mqtt_on_connect(self: Blink2Mqtt, client: Client, userdata: Any, flags: dict, reason_code: ReasonCode, properties: MQTTMessageInfo) -> None:
        if reason_code.value != 0:
            self.logger.error(f"MQTT failed to connect ({reason_code.getName()})")
            self.running = False
            return

        self.publish_service_discovery()
        self.publish_service_availability()
        self.publish_service_state()

        self.logger.info("Subscribing to topics on MQTT")
        client.subscribe("homeassistant/status")
        client.subscribe(f"{self.service_slug}/service/+/set")
        client.subscribe(f"{self.service_slug}/service/+/command")
        client.subscribe(f"{self.service_slug}/switch/#")

    def mqtt_on_disconnect(self: Blink2Mqtt, client: Client, userdata: Any, flags: dict, reason_code: ReasonCode, properties: MQTTMessageInfo) -> None:
        if reason_code.value != 0:
            self.logger.error(f"MQTT lost connection ({reason_code.getName()})")
        else:
            self.logger.info("Closed MQTT connection")

        if self.running and (self.mqtt_connect_time is None or datetime.now() > self.mqtt_connect_time + timedelta(seconds=10)):
            # lets use a new client_id for a reconnect attempt
            self.client_id = self.mqtt_helper.client_id()
            self.mqttc_create()
        else:
            self.logger.info("MQTT disconnect — stopping service loop")
            self.running = False

    def mqtt_on_log(self: Blink2Mqtt, client: Client, userdata: Any, paho_log_level: LogLevel, msg: str) -> None:
        if paho_log_level == LogLevel.MQTT_LOG_ERR:
            self.logger.error(f"MQTT logged: {msg}")
        if paho_log_level == LogLevel.MQTT_LOG_WARNING:
            self.logger.warning(f"MQTT logged: {msg}")

    def mqtt_on_message(self: Blink2Mqtt, client: Client, userdata: Any, msg: MQTTMessage) -> None:
        topic = msg.topic
        payload = self._decode_payload(msg.payload)
        components = topic.split("/")

        if not topic or not payload:
            self.logger.error(f"Got invalid message on topic: {topic or "undef"} with {payload or "undef"}")
            return

        self.logger.debug(f"Got message on topic: {topic} with {payload}")

        # Dispatch based on type of message
        if components[0] == self.mqtt_config["discovery_prefix"] and payload:
            return self._handle_homeassistant_message(payload)

        if components[0] == self.service_slug and components[1] == "service" and payload:
            return self.handle_service_command(components[2], payload)

        if components[0] == self.service_slug:
            return self._handle_device_topic(components, payload)

        self.logger.debug(f"Ignoring unrelated MQTT topic: {topic}")

    def _decode_payload(self: Blink2Mqtt, raw: bytes) -> Any:
        """Try to decode MQTT payload as JSON, fallback to UTF-8 string, else None."""
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
            # Fallback: try to decode as UTF-8 string
            try:
                return raw.decode("utf-8")
            except Exception:
                self.logger.warning("Failed to decode MQTT payload")
                return None

    def _handle_homeassistant_message(self: Blink2Mqtt, payload: str) -> None:
        if payload == "online":
            self.rediscover_all()
            self.logger.info("Home Assistant came online — rediscovering devices")

    def _handle_device_topic(self: Blink2Mqtt, components: list[str], payload: str) -> None:
        parsed = self._parse_device_topic(components)
        if not parsed:
            return

        (vendor, device_id, attribute) = parsed
        if not vendor or not vendor.startswith(self.service_slug):
            self.logger.error(f"Ignoring non-Blink device command, got vendor {vendor}")
            return
        if not device_id or not attribute:
            self.logger.error(f"Failed to parse device_id and/or payload from mqtt topic components: {components}")
            return
        if not self.devices.get(device_id, None):
            self.logger.warning(f"Got MQTT message for unknown device: {device_id}")
            return

        self.logger.info(f"Got message for {self.get_device_name(device_id)}: set {components[-2]} to {payload}")
        asyncio.run_coroutine_threadsafe(self.handle_device_command(device_id, attribute, payload), self.loop)

    def _parse_device_topic(self: Blink2Mqtt, components: list[str]) -> list[str | None] | None:
        """Extract (vendor, device_id, attribute) from an MQTT topic components list (underscore-delimited)."""
        try:
            if components[-1] != "set":
                return None

            # Example topics:
            # blink2mqtt/switch/blink2mqtt_G8xxxxxxxxxxxx/motion_detection/set

            # Case 1: .../<device>/<attribute>/set
            if len(components) >= 5 and "_" in components[-3]:
                vendor, device_id = components[-3].split("_", 1)
                attribute = components[-2]

            # Case 2: .../<device>/set
            elif len(components) >= 4 and "_" in components[-2]:
                vendor, device_id = components[-2].split("_", 1)
                attribute = None

            else:
                raise ValueError(f"Malformed topic (expected underscore): {'/'.join(components)}")
            return [vendor, device_id, attribute]

        except Exception as e:
            self.logger.warning(f"Malformed device topic: {components} ({e})")
            return None

    def safe_split_device(self: Blink2Mqtt, topic: str, segment: str) -> list[str]:
        """Split a topic segment into (vendor, device_id) safely."""
        try:
            return segment.split("-", 1)
        except ValueError:
            self.logger.warning(f"Ignoring malformed topic: {topic}")
            return []

    def set_discovered(self: Blink2Mqtt, device_id: str) -> None:
        self.upsert_state(device_id, internal={"discovered": True})

    def mqtt_on_subscribe(self: Blink2Mqtt, client: Client, userdata: Any, mid: int, reason_code_list: list[ReasonCode], properties: Properties) -> None:
        reason_names = [rc.getName() for rc in reason_code_list]
        joined = "; ".join(reason_names) if reason_names else "none"
        self.logger.debug(f"MQTT subscribed (mid={mid}): {joined}")

    def mqtt_safe_publish(self: Blink2Mqtt, topic: str, payload: str | bool | int | dict, **kwargs: Any) -> None:
        if isinstance(payload, dict) and ("component" in payload or "//////" in payload):
            self.logger.warning("Questionable payload includes 'component' or string of slashes - wont't send to HA")
            self.logger.warning(f"topic: {topic}")
            self.logger.warning(f"payload: {payload}")
            raise ValueError("Possible invalid payload. topic: {topic} payload: {payload}")
        try:
            self.mqttc.publish(topic, cast(PayloadType, payload), **kwargs)
        except Exception as e:
            self.logger.warning(f"MQTT publish failed for {topic} with {payload}: {e}")
