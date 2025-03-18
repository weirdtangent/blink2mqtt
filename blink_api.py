# This software is licensed under the MIT License, which allows you to use,
# copy, modify, merge, publish, distribute, and sell copies of the software,
# with the requirement to include the original copyright notice and this
# permission notice in all copies or substantial portions of the software.
#
# The software is provided 'as is', without any warranty.

from blink import BlinkCamera, BlinkError, CommError, LoginError, exceptions
import asyncio
from asyncio import timeout
import base64
from datetime import datetime
import httpx
import logging
import os
import time
from util import *
from zoneinfo import ZoneInfo

class BlinkAPI(object):
    def __init__(self, config):
        self.logger = logging.getLogger(__name__)

        # we don't want to get this mess of deeper-level logging
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
        logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
        logging.getLogger("blink.http").setLevel(logging.ERROR)
        logging.getLogger("blink.event").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

        self.last_call_date = ''
        self.timezone = config['timezone']

        self.blink_config = config['blink']

        self.count = len(self.blink_config['hosts'])
        self.devices = {}
        self.events = []

    async def connect_to_devices(self):
        self.logger.info(f'Connecting to: {self.blink_config["hosts"]}')

        tasks = []
        for host in self.blink_config['hosts']:
            device_name = self.blink_config['names'].pop(0)
            task = asyncio.create_task(self.get_device(host, device_name))
            tasks.append(task)
        await asyncio.gather(*tasks, return_exceptions=True)

        if len(self.devices) == 0:
            self.logger.error('Failed to connect to all devices, exiting')
            exit(1)

        # return just the config of each device, not the camera object
        return {d: self.devices[d]['config'] for d in self.devices.keys()}

    def get_camera(self, host):
        config = self.blink_config
        return BlinkCamera(host, config['port'], config['username'], config['password'], verbose=False).camera

    async def get_device(self, host, device_name):
        try:
            camera = self.get_camera(host)

            device_type = camera.device_type.replace('type=', '').strip()
            is_ad110 = device_type == 'AD110'
            is_ad410 = device_type == 'AD410'
            is_doorbell = is_ad110 or is_ad410

            serial_number = camera.serial_number
            if not isinstance(serial_number, str):
                self.logger.error(f'Error fetching serial number for {host}: {camera.serial_number}')
                exit(1)

            version = camera.software_information[0].replace('version=', '').strip()
            build = camera.software_information[1].strip()
            sw_version = f'{version} ({build})'

            network_config = dict(item.split('=') for item in camera.network_config.splitlines())
            interface = network_config['table.Network.DefaultInterface']
            ip_address = network_config[f'table.Network.{interface}.IPAddress']
            mac_address = network_config[f'table.Network.{interface}.PhysicalAddress'].upper()

            action = 'Connected' if camera.serial_number not in self.devices else 'Reconnected'
            self.logger.info(f'{action} to {host} as {camera.serial_number}')

            self.devices[serial_number] = {
                'camera': camera,
                'config': {
                    'host': host,
                    'device_name': device_name,
                    'device_type': device_type,
                    'device_class': camera.device_class,
                    'is_ad110': is_ad110,
                    'is_ad410': is_ad410,
                    'is_doorbell': is_doorbell,
                    'serial_number': serial_number,
                    'software_version': sw_version,
                    'hardware_version': camera.hardware_version,
                    'vendor': camera.vendor_information,
                    'network': {
                        'interface': interface,
                        'ip_address': ip_address,
                        'mac': mac_address,
                    }
                },
            }
            self.get_privacy_mode(serial_number)

        except LoginError as err:
            self.logger.error(f'Invalid username/password to connect to device "{host}", fix in config.yaml')
        except BlinkError as err:
            self.logger.error(f'Failed to connect to device "{host}", check config.yaml and restart to try again: {err}')

    # Storage stats -------------------------------------------------------------------------------

    def get_storage_stats(self, device_id):
        try:
            storage = self.devices[device_id]["camera"].storage_all
        except CommError as err:
            self.logger.error(f'Failed to communicate with device ({device_id}) for storage stats')
        except LoginError as err:
            self.logger.error(f'Failed to authenticate with device ({device_id}) for storage stats')

        return {
            'used_percent': str(storage['used_percent']),
            'used': to_gb(storage['used']),
            'total': to_gb(storage['total']),
        }

    # Privacy config ------------------------------------------------------------------------------

    def get_privacy_mode(self, device_id):
        device = self.devices[device_id]

        try:
            privacy = device["camera"].privacy_config().split()
            privacy_mode = True if privacy[0].split('=')[1] == 'true' else False
            device['privacy_mode'] = privacy_mode
        except CommError as err:
            self.logger.error(f'Failed to communicate with device ({device_id}) to get privacy mode')
        except LoginError as err:
            self.logger.error(f'Failed to authenticate with device ({device_id}) to get privacy mode')

        return privacy_mode


    def set_privacy_mode(self, device_id, switch):
        device = self.devices[device_id]

        try:
            response = device["camera"].set_privacy(switch).strip()
        except CommError as err:
            self.logger.error(f'Failed to communicate with device ({device_id}) to set privacy mode')
        except LoginError as err:
            self.logger.error(f'Failed to authenticate with device ({device_id}) to set privacy mode')
        return response

    # Motion detection config ---------------------------------------------------------------------

    def get_motion_detection(self, device_id):
        device = self.devices[device_id]

        try:
            motion_detection = device["camera"].is_motion_detector_on()
        except CommError as err:
            self.logger.error(f'Failed to communicate with device ({device_id}) to get motion detection')
        except LoginError as err:
            self.logger.error(f'Failed to authenticate with device ({device_id}) to get motion detection')

        return motion_detection

    def set_motion_detection(self, device_id, switch):
        device = self.devices[device_id]

        try:
            response = device["camera"].set_motion_detection(switch)
        except CommError as err:
            self.logger.error(f'Failed to communicate with device ({device_id}) to set motion detections')
        except LoginError as err:
            self.logger.error(f'Failed to authenticate with device ({device_id}) to set motion detections')

        return response

    # Snapshots -----------------------------------------------------------------------------------

    async def collect_all_device_snapshots(self):
        tasks = [self.get_snapshot_from_device(device_id) for device_id in self.devices]
        await asyncio.gather(*tasks)

    async def get_snapshot_from_device(self, device_id):
        device = self.devices[device_id]

        tries = 0
        while tries < 3:
            try:
                if 'privacy_mode' not in device or device['privacy_mode'] == False:
                    image = await device["camera"].async_snapshot()
                    device['snapshot'] = base64.b64encode(image)
                    self.logger.debug(f'Processed snapshot from ({device_id}) {len(image)} bytes raw, and {len(device['snapshot'])} bytes base64')
                    break
                else:
                    self.logger.info(f'Skipped snapshot from ({device_id}) because "privacy mode" is ON')
                    break
            except CommError as err:
                tries += 1
            except LoginError as err:
                tries += 1

        if tries == 3:
            self.logger.error(f'Failed to communicate with device ({device_id}) to get snapshot')

    def get_snapshot(self, device_id):
        return self.devices[device_id]['snapshot'] if 'snapshot' in self.devices[device_id] else None

    # Recorded file -------------------------------------------------------------------------------
    def get_recorded_file(self, device_id, file):
        device = self.devices[device_id]

        tries = 0
        while tries < 3:
            try:
                data_raw = device["camera"].download_file(file)
                if data_raw:
                    data_base64 = base64.b64encode(data_raw)
                    self.logger.info(f'Processed recording from ({device_id}) {len(data_raw)} bytes raw, and {len(data_base64)} bytes base64')
                    if len(data_base64) < 100 * 1024 * 1024 * 1024:
                        return data_base64
                    else:
                        self.logger.error(f'Processed recording is too large')
                        return
            except CommError as err:
                tries += 1
            except LoginError as err:
                tries += 1

        if tries == 3:
            self.logger.error(f'Failed to communicate with device ({device_id}) to get recorded file')


    # Events --------------------------------------------------------------------------------------

    async def collect_all_device_events(self):
        tasks = [self.get_events_from_device(device_id) for device_id in self.devices]
        await asyncio.gather(*tasks)

    async def get_events_from_device(self, device_id):
        device = self.devices[device_id]

        tries = 0
        while tries < 3:
            try:
                async for code, payload in device["camera"].async_event_actions("All"):
                    await self.process_device_event(device_id, code, payload)
            except CommError as err:
                tries += 1
            except LoginError as err:
                tries += 1

        if tries == 3:
            self.logger.error(f'Failed to communicate for events for device ({device_id})')

    async def process_device_event(self, device_id, code, payload):
        try:
            device = self.devices[device_id]
            config = device['config']

            # if code != 'NewFile' and code != 'InterVideoAccess':
            #     self.logger.info(f'Event on {device_id} - {code}: {payload}')

            if ((code == 'ProfileAlarmTransmit' and config['is_ad110'])
            or (code == 'VideoMotion' and not config['is_ad110'])):
                motion_payload = {
                    'state': 'on' if payload['action'] == 'Start' else 'off',
                    'region': ', '.join(payload['data']['RegionName'])
                }
                self.events.append({ 'device_id': device_id, 'event': 'motion', 'payload': motion_payload })
            elif code == 'CrossRegionDetection' and payload['data']['ObjectType'] == 'Human':
                human_payload = 'on' if payload['action'] == 'Start' else 'off'
                self.events.append({ 'device_id': device_id, 'event': 'human', 'payload': human_payload })
            elif code == '_DoTalkAction_':
                doorbell_payload = 'on' if payload['data']['Action'] == 'Invite' else 'off'
                self.events.append({ 'device_id': device_id, 'event': 'doorbell', 'payload': doorbell_payload })
            elif code == 'NewFile':
                if ('File' in payload['data'] and '[R]' not in payload['data']['File']
                and ('StoragePoint' not in payload['data'] or payload['data']['StoragePoint'] != 'Temporary')):
                    file_payload = { 'file': payload['data']['File'], 'size': payload['data']['Size'] }
                    self.events.append({ 'device_id': device_id, 'event': 'recording', 'payload': file_payload })
            elif code == 'LensMaskOpen':
                device['privacy_mode'] = True
                self.events.append({ 'device_id': device_id, 'event': 'privacy_mode', 'payload': 'on' })
            elif code == 'LensMaskClose':
                device['privacy_mode'] = False
                self.events.append({ 'device_id': device_id, 'event': 'privacy_mode', 'payload': 'off' })
            # lets send these but not bother logging them here
            elif code == 'TimeChange':
                self.events.append({ 'device_id': device_id, 'event': code , 'payload': payload['action'] })
            elif code == 'NTPAdjustTime':
                self.events.append({ 'device_id': device_id, 'event': code , 'payload': payload['action'] })
            elif code == 'RtspSessionDisconnect':
                self.events.append({ 'device_id': device_id, 'event': code , 'payload': payload['action'] })
            # lets just ignore these
            elif code == 'InterVideoAccess': # I think this is US, accessing the API of the camera, lets not inception!
                pass
            elif code == 'VideoMotionInfo':
                pass
            # save everything else as a 'generic' event
            else:
                self.logger.info(f'Event on {device_id} - {code}: {payload}')
                self.events.append({ 'device_id': device_id, 'event': code , 'payload': payload })
        except Exception as err:
            self.logger.error(f'Failed to process event from {device_id}: {err}', exc_info=True)

    def get_next_event(self):
        return self.events.pop(0) if len(self.events) > 0 else None