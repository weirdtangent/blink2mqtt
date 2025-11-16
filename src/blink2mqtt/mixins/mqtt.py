# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
import asyncio
import concurrent.futures
from datetime import datetime, timedelta
import json
import paho.mqtt.client as mqtt
from paho.mqtt.client import Client, MQTTMessage, ConnectFlags, DisconnectFlags
from paho.mqtt.enums import LogLevel
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode
from paho.mqtt.enums import CallbackAPIVersion
import ssl
from typing import TYPE_CHECKING, Any, Callable, Coroutine, TypeVar

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt

_T = TypeVar("_T")


class MqttError(ValueError):
    """Raised when the connection to the MQTT server fails"""

    pass


class MqttMixin:
    async def mqttc_create(self: Blink2Mqtt) -> None:
        # lets use a new client_id for each connection attempt
        self.client_id = self.mqtt_helper.client_id()
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

        self.mqttc.on_connect = self._wrap_async(self.mqtt_on_connect)
        self.mqttc.on_disconnect = self._wrap_async(self.mqtt_on_disconnect)
        self.mqttc.on_message = self._wrap_async(self.mqtt_on_message)
        self.mqttc.on_subscribe = self._wrap_async(self.mqtt_on_subscribe)
        self.mqttc.on_log = self._wrap_async(self.mqtt_on_log)

        # Define a "last will" message (LWT):
        self.mqttc.will_set(self.mqtt_helper.avty_t("service"), "offline", qos=1, retain=True)

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

    def _wrap_async(
        self: Blink2Mqtt,
        coro_func: Callable[..., Coroutine[Any, Any, _T]],
    ) -> Callable[..., None]:
        def wrapper(*args: Any, **kwargs: Any) -> None:
            self.loop.call_soon_threadsafe(lambda: asyncio.create_task(coro_func(*args, **kwargs)))

        return wrapper

    async def mqtt_on_connect(
        self: Blink2Mqtt, client: Client, userdata: dict[str, Any], flags: ConnectFlags, reason_code: ReasonCode, properties: Properties | None
    ) -> None:
        if reason_code.value != 0:
            raise MqttError(f"MQTT failed to connect ({reason_code.getName()})")

        # send our helper the client
        self.mqtt_helper.set_client(self.mqttc)

        await self.publish_service_discovery()
        await self.publish_service_availability()
        await self.publish_service_state()

        self.logger.info("Subscribing to topics on MQTT")
        client.subscribe("homeassistant/status")
        client.subscribe(f"{self.mqtt_helper.service_slug}/service/+/set")
        client.subscribe(f"{self.mqtt_helper.service_slug}/service/+/command")
        client.subscribe(f"{self.mqtt_helper.service_slug}/+/switch/+/set")

    async def mqtt_on_disconnect(
        self: Blink2Mqtt, client: Client, userdata: Any, flags: DisconnectFlags, reason_code: ReasonCode, properties: Properties | None
    ) -> None:
        # clear the client on our helper
        self.mqtt_helper.clear_client()

        if reason_code.value != 0:
            self.logger.error(f"MQTT lost connection ({reason_code.getName()})")
        else:
            self.logger.info("Closed MQTT connection")

        if self.running and (self.mqtt_connect_time is None or datetime.now() > self.mqtt_connect_time + timedelta(seconds=10)):
            await self.mqttc_create()
        else:
            self.logger.info("MQTT disconnect — stopping service loop")
            self.running = False

    async def mqtt_on_log(self: Blink2Mqtt, client: Client, userdata: Any, paho_log_level: int, msg: str) -> None:
        if paho_log_level == LogLevel.MQTT_LOG_ERR:
            self.logger.error(f"MQTT logged: {msg}")
        if paho_log_level == LogLevel.MQTT_LOG_WARNING:
            self.logger.warning(f"MQTT logged: {msg}")

    async def mqtt_on_message(self: Blink2Mqtt, client: Client, userdata: Any, msg: MQTTMessage) -> None:
        topic = msg.topic
        components = topic.split("/")

        try:
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
            try:
                payload = msg.payload.decode("utf-8")
            except Exception:
                self.logger.warning("failed to decode MQTT payload: {err}")
                return None

        if components[0] == self.mqtt_config["discovery_prefix"] and payload:
            return await self.handle_homeassistant_message(payload)

        if components[0] == self.mqtt_helper.service_slug and components[1] == "service":
            return await self.handle_service_command(components[2], payload)

        if components[0] == self.mqtt_helper.service_slug:
            return await self.handle_device_topic(components, payload)

        self.logger.debug(f"Ignoring unrelated MQTT topic: {topic}")

    async def handle_homeassistant_message(self: Blink2Mqtt, payload: str) -> None:
        if payload == "online":
            await self.rediscover_all()
            self.logger.info("Home Assistant came online — rediscovering devices")

    async def handle_device_topic(self: Blink2Mqtt, components: list[str], payload: Any) -> None:
        parsed = self._parse_device_topic(components)
        if not parsed:
            return

        (vendor, device_id, attribute) = parsed
        if not vendor or not vendor.startswith(self.mqtt_helper.service_slug):
            self.logger.error(f"Ignoring non-Blink device command, got vendor {vendor}")
            return
        if not device_id or not attribute:
            self.logger.error(f"Failed to parse device_id and/or payload from mqtt topic components: {components}")
            return
        if not self.devices.get(device_id, None):
            self.logger.warning(f"Got MQTT message for unknown device: {device_id}")
            return

        self.logger.info(f"Got message for {self.get_device_name(device_id)}: set {components[-2]} to {payload}")
        await self.handle_device_command(device_id, attribute, payload)

    def _parse_device_topic(self: Blink2Mqtt, components: list[str]) -> list[str | None] | None:
        """Extract (vendor, device_id, attribute) from an MQTT topic components list (underscore-delimited)."""
        try:
            if components[-1] != "set":
                return None

            # Example topics:
            # blink2mqtt/blink2mqtt_G8xxxxxxxxxxxx/switch/motion_detection/set

            vendor, device_id = components[1].split("_", 1)
            attribute = components[-2]

            return [vendor, device_id, attribute]

        except Exception as err:
            self.logger.warning(f"Malformed device topic: {components} ({err})")
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

    async def mqtt_on_subscribe(self: Blink2Mqtt, client: Client, userdata: Any, mid: int, reason_code_list: list[ReasonCode], properties: Properties) -> None:
        reason_names = [rc.getName() for rc in reason_code_list]
        joined = "; ".join(reason_names) if reason_names else "none"
        self.logger.debug(f"MQTT subscribed (mid={mid}): {joined}")

    def log_future_result(self: Blink2Mqtt, fut: concurrent.futures.Future) -> None:
        try:
            fut.result()
        except Exception as err:
            self.logger.exception(f"Device command task failed: {err}")
