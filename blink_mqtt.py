# This software is licensed under the MIT License, which allows you to use,
# copy, modify, merge, publish, distribute, and sell copies of the software,
# with the requirement to include the original copyright notice and this
# permission notice in all copies or substantial portions of the software.
#
# The software is provided 'as is', without any warranty.

import asyncio
from datetime import datetime
import blink_api
import json
import logging
import paho.mqtt.client as mqtt
import random
import signal
import ssl
import string
import time
from util import *
from zoneinfo import ZoneInfo

class BlinkMqtt(object):
    def __init__(self, config):
        self.running = False
        self.paused = False
        self.logger = logging.getLogger(__name__)

        self.mqttc = None
        self.mqtt_connect_time = None

        self.config = config
        self.mqtt_config = config['mqtt']
        self.blink_config = config['blink']
        self.timezone = config['timezone']
        self.version = config['version']

        self.storage_update_interval = config['blink'].get('storage_update_interval', 900)
        self.snapshot_update_interval = config['blink'].get('snapshot_update_interval', 300)
        self.discovery_complete = False

        self.client_id = self.get_new_client_id()
        self.service_name = self.mqtt_config['prefix'] + ' service'
        self.service_slug = self.mqtt_config['prefix'] + '-service'

        self.configs = {}
        self.states = {}

    def __enter__(self):
        self.mqttc_create()
        self.blinkc = blink_api.BlinkAPI(self.config)
        self.running = True

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.running = False
        self.logger.info('Exiting gracefully')

        if self.mqttc is not None and self.mqttc.is_connected():
            self.mqttc.disconnect()
        else:
            self.logger.info('Lost connection to MQTT')

    # MQTT Functions ------------------------------------------------------------------------------

    def mqtt_on_connect(self, client, userdata, flags, rc, properties):
        if rc != 0:
            self.logger.error(f'MQTT connection issue ({rc})')
            exit()

        self.logger.info(f'MQTT connected as {self.client_id}')
        client.subscribe(self.get_device_sub_topic())
        client.subscribe(self.get_attribute_sub_topic())

    def mqtt_on_disconnect(self, client, userdata, flags, rc, properties):
        self.logger.info('MQTT connection closed')
        self.mqttc.loop_stop()

        if self.running and time.time() > self.mqtt_connect_time + 10:
            self.paused = True
            self.logger.info('Sleeping for 30 seconds to give MQTT time to relax')
            time.sleep(30)

            # lets use a new client_id for a reconnect
            self.client_id = self.get_new_client_id()
            self.mqttc_create()
            self.paused = False
        else:
            self.running = False
            exit()

    def mqtt_on_log(self, client, userdata, paho_log_level, msg):
        if paho_log_level == mqtt.LogLevel.MQTT_LOG_ERR:
            self.logger.error(f'MQTT LOG: {msg}')
        elif paho_log_level == mqtt.LogLevel.MQTT_LOG_WARNING:
            self.logger.warn(f'MQTT LOG: {msg}')

    def mqtt_on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            payload = msg.payload.decode('utf-8')
        except:
            self.logger.error('Failed to understand MQTT message, ignoring')
            return

        # we might get:
        #   */service/set
        #   */service/set/attribute
        #   */device/component/set
        #   */device/component/set/attribute
        components = topic.split('/')

        # handle this message if it's for us, otherwise pass along to blink API
        if components[-2] == self.get_component_slug('service'):
            self.handle_service_message(None, payload)
        elif components[-3] == self.get_component_slug('service'):
            self.handle_service_message(components[-1], payload)
        else:
            if components[-1] == 'set':
                vendor, device_id = components[-2].split('-')
            elif components[-2] == 'set':
                vendor, device_id = components[-3].split('-')
                attribute = components[-1]

            # of course, we only care about our 'blink-<serial>' messages
            if not vendor or vendor != 'blink':
                return

            # ok, it's for us, lets announce it
            self.logger.debug(f'Incoming MQTT message for {topic} - {payload}')

            # if we only got back a scalar value, lets turn it into a dict with
            # the attribute name after `/set/` in the command topic
            if not isinstance(payload, dict) and attribute:
                payload = { attribute: payload }

            # if we just started, we might get messages immediately, lets
            # wait up to 3 min for devices to show up before we ignore the message
            checks = 0
            while device_id not in self.states:
                checks += 1
                # we'll try for 3 min, and then give up
                if checks > 36:
                    self.logger.warn(f"Got MQTT message for a device we don't know: {device_id}")
                    return
                time.sleep(5)

            self.logger.info(f'Got MQTT message for: {self.get_device_name(device_id)} - {payload}')

            # ok, lets format the device_id (not needed) and send to blink
            self.send_command(device_id, payload)

    def mqtt_on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        rc_list = map(lambda x: x.getName(), reason_code_list)
        self.logger.debug(f'MQTT SUBSCRIBED: reason_codes - {'; '.join(rc_list)}')

    # MQTT Helpers --------------------------------------------------------------------------------

    def mqttc_create(self):
        self.mqttc = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=False,
            reconnect_on_failure=False,
        )

        if self.mqtt_config.get('tls_enabled'):
            self.mqttcnt.tls_set(
                ca_certs=self.mqtt_config.get('tls_ca_cert'),
                certfile=self.mqtt_config.get('tls_cert'),
                keyfile=self.mqtt_config.get('tls_key'),
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS,
            )
        else:
            self.mqttc.username_pw_set(
                username=self.mqtt_config.get('username'),
                password=self.mqtt_config.get('password'),
            )

        self.mqttc.on_connect = self.mqtt_on_connect
        self.mqttc.on_disconnect = self.mqtt_on_disconnect
        self.mqttc.on_message = self.mqtt_on_message
        self.mqttc.on_subscribe = self.mqtt_on_subscribe
        self.mqttc.on_log = self.mqtt_on_log

        # will_set for service device
        self.mqttc.will_set(self.get_discovery_topic('service', 'availability'), payload="offline", qos=self.mqtt_config['qos'], retain=True)

        try:
            self.mqttc.connect(
                self.mqtt_config.get('host'),
                port=self.mqtt_config.get('port'),
                keepalive=60,
            )
            self.mqtt_connect_time = time.time()
            self.mqttc.loop_start()
        except ConnectionError as error:
            self.logger.error(f'COULD NOT CONNECT TO MQTT {self.mqtt_config.get("host")}: {error}')
            exit(1)

    # MQTT Topics ---------------------------------------------------------------------------------

    def get_new_client_id(self):
        return self.mqtt_config['prefix'] + '-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    def get_device_name(self, device_id):
        if device_id not in self.configs or 'device' not in self.configs[device_id] or 'name' not in self.configs[device_id]['device']:
            return f'<{device_id}>'
        return self.configs[device_id]['device']['name']

    def get_slug(self, device_id, type):
        return f"blink_{device_id.replace(':','')}_{type}"

    def get_device_sub_topic(self):
        if 'homeassistant' not in self.mqtt_config or self.mqtt_config['homeassistant'] == False:
            return f"{self.mqtt_config['prefix']}/+/set"
        return f"{self.mqtt_config['discovery_prefix']}/device/+/set"

    def get_attribute_sub_topic(self):
        if 'homeassistant' not in self.mqtt_config or self.mqtt_config['homeassistant'] == False:
            return f"{self.mqtt_config['prefix']}/+/set"
        return f"{self.mqtt_config['discovery_prefix']}/device/+/set/+"

    def get_component_slug(self, device_id):
        return f"blink-{device_id.replace(':','')}"

    def get_command_topic(self, device_id, attribute_name):
        if attribute_name:
            if 'homeassistant' not in self.mqtt_config or self.mqtt_config['homeassistant'] == False:
                return f"{self.mqtt_config['prefix']}/{self.get_component_slug(device_id)}/set/{attribute_name}"
            return f"{self.mqtt_config['discovery_prefix']}/device/{self.get_component_slug(device_id)}/set/{attribute_name}"
        else:
            if 'homeassistant' not in self.mqtt_config or self.mqtt_config['homeassistant'] == False:
                return f"{self.mqtt_config['prefix']}/{self.get_component_slug(device_id)}/set"
            return f"{self.mqtt_config['discovery_prefix']}/device/{self.get_component_slug(device_id)}/set"

    def get_discovery_topic(self, device_id, topic):
        if 'homeassistant' not in self.mqtt_config or self.mqtt_config['homeassistant'] == False:
            return f"{self.mqtt_config['prefix']}/{self.get_component_slug(device_id)}/{topic}"
        return f"{self.mqtt_config['discovery_prefix']}/device/{self.get_component_slug(device_id)}/{topic}"

    def get_discovery_topic(self, device_id, topic):
        if 'homeassistant' not in self.mqtt_config or self.mqtt_config['homeassistant'] == False:
            return f"{self.mqtt_config['prefix']}/{self.get_component_slug(device_id)}/{topic}"
        return f"{self.mqtt_config['discovery_prefix']}/device/{self.get_component_slug(device_id)}/{topic}"

    def get_discovery_subtopic(self, device_id, topic, subtopic):
        if 'homeassistant' not in self.mqtt_config or self.mqtt_config['homeassistant'] == False:
            return f"{self.mqtt_config['prefix']}/{self.get_component_slug(device_id)}/{topic}/{subtopic}"
        return f"{self.mqtt_config['discovery_prefix']}/device/{self.get_component_slug(device_id)}/{topic}/{subtopic}"

    # Service Device ------------------------------------------------------------------------------

    def publish_service_state(self):
        if 'service' not in self.states:
            self.states['service'] = {
                'availability': 'online',
                'state': { 'state': 'ON' },
                'intervals': {},
            }

        service_states = self.states['service']

        # update states
        service_states['state'] = {
            'state': 'ON',
        }
        service_states['intervals'] = {
            'storage_refresh': self.storage_update_interval,
            'snapshot_refresh': self.snapshot_update_interval,
        }

        for topic in ['state','availability','intervals']:
            if topic in service_states:
                payload = json.dumps(service_states[topic]) if isinstance(service_states[topic], dict) else service_states[topic]
                self.mqttc.publish(self.get_discovery_topic('service', topic), payload, qos=self.mqtt_config['qos'], retain=True)

    def publish_service_device(self):
        state_topic = self.get_discovery_topic('service', 'state')
        command_topic = self.get_discovery_topic('service', 'set')
        availability_topic = self.get_discovery_topic('service', 'availability')

        self.mqttc.publish(
            self.get_discovery_topic('service','config'),
            json.dumps({
                'qos': self.mqtt_config['qos'],
                'state_topic': state_topic,
                'availability_topic': availability_topic,
                'device': {
                    'name': self.service_name,
                    'ids': self.service_slug,
                    'suggested_area': 'House',
                    'manufacturer': 'weirdTangent',
                    'model': self.version,
                },
                'origin': {
                    'name': self.service_name,
                    'sw_version': self.version,
                    'support_url': 'https://github.com/weirdtangent/blink2mqtt',
                },
                'components': {
                    self.service_slug + '_status': {
                        'name': 'Service',
                        'platform': 'binary_sensor',
                        'schema': 'json',
                        'payload_on': 'ON',
                        'payload_off': 'OFF',
                        'icon': 'mdi:language-python',
                        'state_topic': state_topic,
                        'value_template': '{{ value_json.state }}',
                        'unique_id': 'blink_service_status',
                    },
                    self.service_slug + '_storage_refresh': {
                        'name': 'Storage Refresh Interval',
                        'platform': 'number',
                        'schema': 'json',
                        'icon': 'mdi:numeric',
                        'min': 10,
                        'max': 3600,
                        'state_topic': self.get_discovery_topic('service', 'intervals'),
                        'command_topic': self.get_command_topic('service', 'storage_refresh'),
                        'value_template': '{{ value_json.storage_refresh }}',
                        'unique_id': 'blink_service_storage_refresh',
                    },
                    self.service_slug + '_snapshot_refresh': {
                        'name': 'Snapshot Refresh Interval',
                        'platform': 'number',
                        'schema': 'json',
                        'icon': 'mdi:numeric',
                        'min': 10,
                        'max': 3600,
                        'state_topic': self.get_discovery_topic('service', 'intervals'),
                        'command_topic': self.get_command_topic('service', 'snapshot_refresh'),
                        'value_template': '{{ value_json.snapshot_refresh }}',
                        'unique_id': 'blink_service_snapshot_refresh',
                    },
                },
            }),
            qos=self.mqtt_config['qos'],
            retain=True
        )

    # Blink Helpers -----------------------------------------------------------------------------

    # setup devices -------------------------------------------------------------------------------

    async def setup_devices(self):
        self.logger.info(f'Setup devices')

        devices = await self.blinkc.connect_to_devices()

        self.publish_service_device()
        for device_id in devices:
            config = devices[device_id]

            if 'device_type' in config:
                first = False
                if device_id not in self.configs:
                    first = True
                    self.configs[device_id] = {}
                    self.states[device_id] = config
                    self.configs[device_id]['qos'] = self.mqtt_config['qos']
                    self.configs[device_id]['state_topic'] = self.get_discovery_topic(device_id, 'state')
                    self.configs[device_id]['availability_topic'] = self.get_discovery_topic('service', 'availability')
                    self.configs[device_id]['command_topic'] = self.get_discovery_topic(device_id, 'set')

                self.configs[device_id]['device'] = {
                    'name': config['device_name'],
                    'manufacturer': config['vendor'],
                    'model': config['device_type'],
                    'ids': device_id,
                    'sw_version': config['software_version'],
                    'hw_version': config['hardware_version'],
                    'connections': [
                        ['host', config['host']],
                        ['mac', config['network']['mac']],
                        ['ip address', config['network']['ip_address']],
                    ],
                    'configuration_url': 'http://' + config['host'] + '/',
                    'via_device': self.service_slug,
                }
                self.configs[device_id]['origin'] = {
                    'name': self.service_name,
                    'sw_version': self.version,
                    'support_url': 'https://github.com/weirdtangent/blink2mqtt',
                }

                # setup initial satte
                self.states[device_id]['state'] = {
                    'state': 'ON',
                    'last_update': str(datetime.now(ZoneInfo(self.timezone))),
                    'host': config['host'],
                    'serial_number': config['serial_number'],
                    'sw_version': config['software_version'],
                }

                self.add_components_to_device(device_id)

                if first:
                    self.logger.info(f'Adding device: "{config['device_name']}" [Blink {config["device_type"]}] ({device_id})')
                    self.publish_device_discovery(device_id)
                else:
                    self.logger.debug(f'Updated device: {self.configs[device_id]['device']['name']}')

            else:
                if first_time_through:
                    self.logger.info(f'Saw device, but not supported yet: "{config["device_name"]}" [blink {config["device_type"]}] ({device_id})')

        # lets log our first time through and then release the hounds
        if not self.discovery_complete:
            self.logger.info('Device setup and discovery is done')
            self.discovery_complete = True

    # add blink components to devices
    def add_components_to_device(self, device_id):
        device_config = self.configs[device_id]
        device_states = self.states[device_id]
        components = {}

        if device_states['is_doorbell']:
            doorbell_name = 'Doorbell' if device_states['device_name'] == 'Doorbell' else f'{device_states["device_name"]} Doorbell'
            components[self.get_slug(device_id, 'doorbell')] = {
                'name': doorbell_name,
                'platform': 'binary_sensor',
                'payload_on': 'on',
                'payload_off': 'off',
                'device_class': '',
                'icon': 'mdi:doorbell',
                'state_topic': self.get_discovery_topic(device_id, 'doorbell'),
                'value_template': '{{ value_json.doorbell }}',
                'unique_id': self.get_slug(device_id, 'doorbell'),
            }
            device_states['doorbell'] = {}

        if device_states['is_ad410']:
            components[self.get_slug(device_id, 'human')] = {
                'name': 'Human',
                'platform': 'binary_sensor',
                'payload_on': 'on',
                'payload_off': 'off',
                'device_class': 'motion',
                'state_topic': self.get_discovery_topic(device_id, 'human'),
                'value_template': '{{ value_json.human }}',
                'unique_id': self.get_slug(device_id, 'human'),
            }
            device_states['human'] = 'off'

        components[self.get_slug(device_id, 'snapshot_camera')] = {
            'name': 'Latest snapshot',
            'platform': 'camera',
            'topic': self.get_discovery_subtopic(device_id, 'camera','snapshot'),
            'image_encoding': 'b64',
            'state_topic': device_config['state_topic'],
            'value_template': '{{ value_json.state }}',
            'unique_id': self.get_slug(device_id, 'snapshot_camera'),
        }
        if 'webrtc' in self.blink_config:
            webrtc_config = self.blink_config['webrtc']
            rtc_host = webrtc_config['host']
            rtc_port = webrtc_config['port']
            rtc_link = webrtc_config['link']
            rtc_source = webrtc_config['sources'].pop(0)
            rtc_url = f'http://{rtc_host}:{rtc_port}/{rtc_link}?src={rtc_source}'
            device_config['device']['configuration_url'] = rtc_url

        # copy the snapshot camera for the eventshot camera, with a couple of changes
        components[self.get_slug(device_id, 'event_camera')] = {
            'name': 'Motion capture',
            'platform': 'image',
            'image_encoding': 'b64',
            'state_topic': device_config['state_topic'],
            'value_template': '{{ value_json.state }}',
            'image_topic': self.get_discovery_subtopic(device_id, 'camera','eventshot'),
            'unique_id': self.get_slug(device_id, 'eventshot_camera'),
          }
        device_states['camera'] = {'snapshot': None, 'eventshot': None}

        components[self.get_slug(device_id, 'privacy_mode')] = {
            'name': 'Privacy mode',
            'platform': 'switch',
            'payload_on': 'on',
            'payload_off': 'off',
            'device_class': 'switch',
            'icon': 'mdi:camera-off',
            'state_topic': self.get_discovery_topic(device_id, 'privacy_mode'),
            'command_topic': self.get_command_topic(device_id, 'privacy_mode'),
            'unique_id': self.get_slug(device_id, 'privacy_mode'),
        }
        device_states['privacy_mode'] = None

        components[self.get_slug(device_id, 'motion_detection')] = {
            'name': 'Motion detection',
            'platform': 'switch',
            'payload_on': 'on',
            'payload_off': 'off',
            'device_class': 'switch',
            'icon': 'mdi:motion-sensor',
            'state_topic': self.get_discovery_topic(device_id, 'motion_detection'),
            'command_topic': self.get_command_topic(device_id, 'motion_detection'),
            'unique_id': self.get_slug(device_id, 'motion_detection'),
        }
        device_states['motion_detection'] = None

        components[self.get_slug(device_id, 'motion')] = {
            'name': 'Motion',
            'platform': 'binary_sensor',
            'payload_on': 'on',
            'payload_off': 'off',
            'device_class': 'motion',
            'state_topic': self.get_discovery_topic(device_id, 'motion'),
            'json_attributes_topic': self.get_discovery_topic(device_id, 'motion'),
            'value_template': '{{ value_json.state }}',
            'unique_id': self.get_slug(device_id, 'motion'),
        }
        components[self.get_slug(device_id, 'motion_region')] = {
            'name': 'Motion region',
            'platform': 'sensor',
            'state_topic': self.get_discovery_topic(device_id, 'motion'),
            'value_template': '{{ value_json.region }}',
            'unique_id': self.get_slug(device_id, 'motion_region'),
        }
        device_states['motion'] = { 'state': 'off', 'region': None }

        components[self.get_slug(device_id, 'version')] = {
            'name': 'Version',
            'platform': 'sensor',
            'icon': 'mdi:package-up',
            'state_topic': device_config['state_topic'],
            'value_template': '{{ value_json.sw_version }}',
            'entity_category': 'diagnostic',
            'unique_id': self.get_slug(device_id, 'sw_version'),
        }

        components[self.get_slug(device_id, 'serial_number')] = {
            'name': 'Serial Number',
            'platform': 'sensor',
            'icon': 'mdi:identifier',
            'state_topic': device_config['state_topic'],
            'value_template': '{{ value_json.serial_number }}',
            'entity_category': 'diagnostic',
            'unique_id': self.get_slug(device_id, 'serial_number'),
        }

        components[self.get_slug(device_id, 'host')] = {
            'name': 'Host',
            'platform': 'sensor',
            'icon': 'mdi:ip-network',
            'state_topic': device_config['state_topic'],
            'value_template': '{{ value_json.host }}',
            'entity_category': 'diagnostic',
            'unique_id': self.get_slug(device_id, 'host'),
        }

        components[self.get_slug(device_id, 'event')] = {
            'name': 'Last event',
            'platform': 'sensor',
            'state_topic': self.get_discovery_topic(device_id, 'event'),
            'unique_id': self.get_slug(device_id, 'event'),
        }
        device_states['event'] = None
        device_states['recording'] = {}

        components[self.get_slug(device_id, 'storage_used_percent')] = {
            'name': 'Storage used %',
            'platform': 'sensor',
            'icon': 'mdi:micro-sd',
            'unit_of_measurement': '%',
            'state_topic': self.get_discovery_topic(device_id, 'storage'),
            'value_template': '{{ value_json.used_percent }}',
            'unique_id': self.get_slug(device_id, 'storage_used_percent'),
        }
        components[self.get_slug(device_id, 'storage_total')] = {
            'name': 'Storage total',
            'platform': 'sensor',
            'icon': 'mdi:micro-sd',
            'unit_of_measurement': 'GB',
            'state_topic': self.get_discovery_topic(device_id, 'storage'),
            'value_template': '{{ value_json.total }}',
            'unique_id': self.get_slug(device_id, 'storage_total'),
        }
        components[self.get_slug(device_id, 'storage_used')] = {
            'name': 'Storage used',
            'platform': 'sensor',
            'icon': 'mdi:micro-sd',
            'unit_of_measurement': 'GB',
            'state_topic': self.get_discovery_topic(device_id, 'storage'),
            'value_template': '{{ value_json.used }}',
            'unique_id': self.get_slug(device_id, 'storage_used'),
        }
        device_states['storage'] = {}

        components[self.get_slug(device_id, 'last_update')] = {
            'name': 'Last Update',
            'platform': 'sensor',
            'device_class': 'timestamp',
            'entity_category': 'diagnostic',
            'state_topic': device_config['state_topic'],
            'value_template': '{{ value_json.last_update }}',
            'unique_id': self.get_slug(device_id, 'last_update'),
        }

        device_config['components'] = components

    def publish_device_state(self, device_id):
        device_states = self.states[device_id]
        device_states['state']['last_update'] = str(datetime.now(ZoneInfo(self.timezone)))

        for topic in ['state','storage','motion','human','doorbell','event','recording','privacy_mode','motion_detection']:
            if topic in device_states:
                publish_topic = self.get_discovery_topic(device_id, topic)
                payload = json.dumps(device_states[topic]) if isinstance(device_states[topic], dict) else device_states[topic]
                self.mqttc.publish(publish_topic, payload, qos=self.mqtt_config['qos'], retain=True)

        for image_type in ['snapshot','eventshot']:
            if image_type in device_states['camera'] and device_states['camera'][image_type] is not None:
                publish_topic = self.get_discovery_subtopic(device_id, 'camera',image_type)
                payload = device_states['camera'][image_type]
                result = self.mqttc.publish(publish_topic, payload, qos=self.mqtt_config['qos'], retain=True)

    def publish_device_discovery(self, device_id):
        device_config = self.configs[device_id]
        payload = json.dumps(device_config)

        self.mqttc.publish(self.get_discovery_topic(device_id, 'config'), payload, qos=self.mqtt_config['qos'], retain=True)

     # refresh * all devices -----------------------------------------------------------------------

    def refresh_storage_all_devices(self):
        self.logger.info(f'Refreshing storage info for all devices (every {self.storage_update_interval} sec)')

        for device_id in self.configs:
            if not self.running: break
            device_states = self.states[device_id]

            # update the privacy mode switch
            # we don't need to verify this often since events should let us know
            privacy_mode = self.blinkc.get_privacy_mode(device_id)
            if privacy_mode is not None:
                device_states['privacy_mode'] = 'on' if privacy_mode == True else 'off'

            # update the motion detection switch
            motion_detection = self.blinkc.get_motion_detection(device_id)
            device_states['motion_detection'] = 'on' if motion_detection == True else 'off'

            storage = self.blinkc.get_storage_stats(device_id)
            if storage is not None:
                device_states['storage'] = storage

            self.publish_service_state()
            self.publish_device_state(device_id)

    def refresh_snapshot_all_devices(self):
        self.logger.info(f'Collecting snapshots for all devices (every {self.snapshot_update_interval} sec)')

        for device_id in self.configs:
            if not self.running: break
            self.refresh_snapshot(device_id,'snapshot')

    # type is 'snapshot' for normal, or 'eventshot' for capturing an image immediately after a "movement" event
    def refresh_snapshot(self, device_id, type):
        device_states = self.states[device_id]

        image = self.blinkc.get_snapshot(device_id)

        if image is None:
            return

        # only store and send to MQTT if the image has changed
        if device_states['camera'][type] is None or device_states['camera'][type] != image:
            device_states['camera'][type] = image
            self.publish_service_state()
            self.publish_device_state(device_id)

    def get_recorded_file(self, device_id, file, type):
        device_states = self.states[device_id]

        self.logger.info(f'Getting recorded file "{file}"')
        image = self.blinkc.get_recorded_file(device_id, file)

        if image is None:
            self.logger.info(f'Failed to get recorded file from {self.get_device_name(device_id)}')
            return

        # only store and send to MQTT if the image has changed
        if device_states['camera'][type] is None or device_states['camera'][type] != image:
            device_states['camera'][type] = image
            self.publish_service_state()
            self.publish_device_state(device_id)

    # send command to Blink  --------------------------------------------------------------------

    def send_command(self, device_id, data):
        device_config = self.configs[device_id]
        device_states = self.states[device_id]

        if data == 'PRESS':
            self.logger.info(f'We got a PRESS command for {self.get_device_name(device_id)}')
            pass
        elif 'privacy_mode' in data:
            set_privacy_to = False if data['privacy_mode'] == 'off' else True
            self.logger.info(f'Setting PRIVACY_MODE to {set_privacy_to} for {self.get_device_name(device_id)}')

            response = self.blinkc.set_privacy_mode(device_id, set_privacy_to)

            # if Blink device was good with that command, lets update state and then MQTT
            if response == 'OK':
                device_states['privacy_mode'] = data['privacy_mode']
                self.publish_device_state(device_id)
            else:
                self.logger.error(f'Setting PRIVACY_MODE failed: {repr(response)}')
        elif 'motion_detection' in data:
            set_motion_detection_to = False if data['motion_detection'] == 'off' else True
            self.logger.info(f'Setting MOTION_DETECTION to {set_motion_detection_to} for {self.get_device_name(device_id)}')

            response = self.blinkc.set_motion_detection(device_id, set_motion_detection_to)

            # if Blink device was good with that command, lets update state and then MQTT
            if response == True:
                device_states['motion_detection'] = data['motion_detection']
                self.publish_device_state(device_id)
            else:
                self.logger.error(f'Setting MOTION_DETECTION failed: {repr(response)}')
        else:
            self.logger.error(f'We got a command ({data}), but do not know what to do')

    def handle_service_message(self, attribute, message):
        match attribute:
            case 'storage_refresh':
                self.storage_update_interval = message
                self.logger.info(f'Updated STORAGE_REFRESH_INTERVAL to be {message}')
            case 'snapshot_refresh':
                self.snapshot_update_interval = message
                self.logger.info(f'Updated SNAPSHOT_REFRESH_INTERVAL to be {message}')
            case _:
                self.logger.info(f'IGNORED UNRECOGNIZED blink-service MESSAGE for {attribute}: {message}')
                return

        self.publish_service_state()

    # collect events and then check queue of events -----------------------------------------------

    async def collect_all_device_events(self):
        await self.blinkc.collect_all_device_events()

    def check_for_events(self):
        try:
            while device_event := self.blinkc.get_next_event():
                if device_event is None:
                    break
                if 'device_id' not in device_event:
                    self.logger(f'Got event, but missing device_id: {device_event}')
                    continue

                device_id = device_event['device_id']
                event = device_event['event']
                payload = device_event['payload']

                device_states = self.states[device_id]

                # if one of our known sensors
                if event in ['motion','human','doorbell','recording','privacy_mode']:
                    if event == 'recording' and payload['file'].endswith('.jpg'):
                        self.get_recorded_file(device_id, payload['file'], 'eventshot')
                    else:
                        # only log details if not a recording
                        if event != 'recording':
                            self.logger.info(f'Got event for {self.get_device_name(device_id)}: {event} - {payload}')
                        device_states[event] = payload

                    # other ways to infer "privacy mode" is off and needs updating
                    if event in ['motion','human','doorbell'] and device_states['privacy_mode'] == 'on':
                        device_states['privacy_mode'] = 'off'
                else:
                    self.logger.info(f'Got {{{event}: {payload}}} for "{self.get_device_name(device_id)}"')
                    device_states['event'] = f'{event}: {payload}'

                self.publish_device_state(device_id)
        except Exception as err:
            self.logger.error(err, exc_info=True)

    # async loops and main loop -------------------------------------------------------------------

    async def _handle_signals(self, signame, loop):
        self.running = False
        self.logger.warn(f'{signame} received, waiting for tasks to cancel...')

        for task in asyncio.all_tasks():
            if not task.done(): task.cancel(f'{signame} received')

    async def collect_storage_info(self):
        while self.running == True:
            if not self.paused: self.refresh_storage_all_devices()
            if self.running: await asyncio.sleep(self.storage_update_interval)

    async def collect_events(self):
        while self.running == True:
            if not self.paused: await self.collect_all_device_events()
            if self.running: await asyncio.sleep(1)

    async def check_event_queue(self):
        while self.running == True:
            if not self.paused: self.check_for_events()
            if self.running: await asyncio.sleep(1)

    async def collect_snapshots(self):
        while self.running == True:
            await self.blinkc.collect_all_device_snapshots()
            if not self.paused: self.refresh_snapshot_all_devices()
            if self.running: await asyncio.sleep(self.snapshot_update_interval)

    # main loop
    async def main_loop(self):
        await self.setup_devices()

        loop = asyncio.get_running_loop()
        tasks = [
            asyncio.create_task(self.collect_storage_info()),
            asyncio.create_task(self.collect_events()),
            asyncio.create_task(self.check_event_queue()),
            asyncio.create_task(self.collect_snapshots()),
        ]

        # setup signal handling for tasks
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig, lambda: asyncio.create_task(self._handle_signals(sig.name, loop))
            )

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    self.running = False
                    self.logger.error(f'Caught exception: {err}', exc_info=True)
        except asyncio.CancelledError:
            exit(1)
        except Exception as err:
            self.running = False
            self.logger.error(f'Caught exception: {err}')