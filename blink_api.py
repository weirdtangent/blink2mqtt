# This software is licensed under the MIT License, which allows you to use,
# copy, modify, merge, publish, distribute, and sell copies of the software,
# with the requirement to include the original copyright notice and this
# permission notice in all copies or substantial portions of the software.
#
# The software is provided 'as is', without any warranty.

import aioconsole
from aiohttp import ClientSession
import asyncio
from asyncio import timeout
from blinkpy.auth import Auth
from blinkpy.blinkpy import Blink
from blinkpy.helpers.util import json_load
import base64
from datetime import datetime
import logging
import os
import time
from util import *
from zoneinfo import ZoneInfo

class BlinkAPI(object):
    def __init__(self, config):
        self.logger = logging.getLogger(__name__)

        # we don't want to get this mess of deeper-level logging
        logging.getLogger("blinkpy.blinkpy").setLevel(logging.WARNING)
        logging.getLogger("blinkpy.sync_module").setLevel(logging.WARNING)

        self.blink_config = config['blink']
        self.timezone = config['timezone']

        self.session = None
        self.blinkc = None

        self.last_call_date = ''
        self.devices = {}
        self.sync_modules = {}
        self.events = []

    async def connect(self):
        self.session = ClientSession()
        self.blinkc = Blink(session=self.session)

        need2fa = False
        if os.path.exists("config/blinkc.cred"):
            auth = Auth(await json_load("config/blinkc.cred"), no_prompt=True)
            if auth.login_attributes["token"] is None:
                self.logger.error('Failed to auth with config/blinkc.cred file. Removing bad file and retrying')
                os.remove('config/blinkc.cred')
                auth = Auth({
                    'username': self.blink_config['username'],
                    'password': self.blink_config['password'],
                }, no_prompt=True)
                need2fa = True
        else:
            auth = Auth({
                'username': self.blink_config['username'],
                'password': self.blink_config['password'],
            }, no_prompt=True)
            need2fa = True
        self.blinkc.auth = auth

        await self.blinkc.start()

        if need2fa:
            self.logger.warn('The 2fa key from Blink will be needed. Save the key into /config/key.txt and I will wait up to 120 seconds for you to do this.')
            seconds = 0
            while seconds < 120:
                if os.path.exists("config/key.txt"):
                    self.logger.info('I see the config/key.txt file, sending the key to Blink and deleting that file')
                    key = read_file('config/key.txt')
                    os.remove('config/key.txt')
                    await auth.send_auth_key(self.blinkc, key)
                    await self.blinkc.setup_post_verify()
                    await self.blinkc.save("config/blinkc.cred")
                    return
                seconds += 1
                time.sleep(1)

            self.logger.error('I did not see the /config/key.txt file in time. Please try again')
            os.remove('config/blinkc.cred')
            os.remove('config/key.txt')
            os._exit(1)

        # can we just go ahead and save this now?
        await self.blinkc.save("config/blinkc.cred")

    async def disconnect(self):
        await self.blinkc.save("config/blinkc.cred")
        await self.session.close()

    async def get_cameras(self):
        for name, camera in self.blinkc.cameras.items():
            attributes = camera.attributes
            self.devices[attributes['serial']] = {
                'config': {
                    'device_name': attributes['name'],
                    'device_type': attributes['type'],
                    'serial_number': attributes['serial'],
                    'software_version': attributes['version'],
                    'vendor': 'Amazon',
                    'sync_module': attributes['sync_module'],
                    'arm_mode': attributes['motion_enabled'],
                    'motion': attributes['motion_detected'],
                    'temperature': attributes['temperature'],
                    'battery': attributes['battery'],
                    'battery_voltage': attributes['battery_voltage'],
                    'wifi_strength': attributes['wifi_strength'],
                    'sync_strength': attributes['sync_signal_strength'],
                }
            }

        return self.devices

    async def get_sync_modules(self):
        for name, sync_module in self.blinkc.sync.items():
            await sync_module.get_network_info()
            network = sync_module.network_info
            attributes = sync_module.attributes

            self.sync_modules[attributes['serial']] = {
                'config': {
                    'device_name': attributes['name'],
                    'device_type': 'sync_module',
                    'serial_number': attributes['serial'],
                    'software_version': attributes['version'],
                    'vendor': 'Amazon',
                    'arm_mode': sync_module.arm,
                    'region_id': attributes['region_id'],
                    'local_storage': attributes['local_storage'],
                }
            }

        return self.sync_modules

    # Arm mode  ----------------------------------------------------------------------------------0

    async def set_arm_mode(self, device_id, switch):
        if device_id in self.devices:
            name = self.devices[device_id]['config']['device_name']
            device = self.blinkc.cameras[name]
        else:
            name = self.sync_modules[device_id]['config']['device_name']
            device = self.blinkc.sync[name]

        try:
            async with asyncio.timeout(5):
                response = await device.async_arm(switch)
                self.logger.info(f'SET ARM MODE: {response}')
                return response
        except asyncio.TimeoutError:
            return "Request timed out"
        except Exception as err:
            self.logger.error(f'Failed to communicate with device ({device_id}) to set arm mode')

    # Motion --------------------------------------------------------------------------------------

    def get_camera_motion(self, device_id):
        name = self.devices[device_id]['config']['device_name']
        device = self.blinkc.cameras[name]

        try:
            motion = device.sync.motion[name]
            self.devices[device_id]['config']['motion'] = motion
        except Exception as err:
            self.logger.error(f'Failed to communicate with device ({device_id}) to get motion detection')

        return motion

    def set_motion_detection(self, device_id, switch):
        device = self.devices[device_id]

        try:
            response = device["camera"].set_motion_detection(switch)
        except Exception as err:
            self.logger.error(f'Failed to communicate with device ({device_id}) to set motion detections')

        return response

    # Snapshots -----------------------------------------------------------------------------------

    async def collect_all_device_snapshots(self):
        tasks = [self.take_snapshot_from_device(device_id) for device_id in self.devices]
        await asyncio.gather(*tasks)

        await self.blinkc.refresh()

        tasks = [self.get_snapshot_from_device(device_id) for device_id in self.devices]
        await asyncio.gather(*tasks)

    async def take_snapshot_from_device(self, device_id):
        device = self.devices[device_id]

        tries = 0
        while tries < 3:
            try:
                camera = self.blinkc.cameras[device['config']['device_name']]
                await camera.snap_picture()
                break
            except Exception as err:
                tries += 1

        if tries == 3:
            self.logger.error(f'Failed to communicate with device ({device_id}) to get snapshot')

    async def get_snapshot_from_device(self, device_id):
        device = self.devices[device_id]

        tries = 0
        while tries < 3:
            try:
                camera = self.blinkc.cameras[device['config']['device_name']]
                image = camera.image_from_cache
                encoded = base64.b64encode(image)
                if 'snapshot' not in device or device['snapshot'] != encoded:
                    device['snapshot'] = encoded
                    self.logger.info(f'Processed NEW snapshot from ({device_id}) {len(image)} bytes raw, and {len(encoded)} bytes base64')
                break
            except Exception as err:
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
            except Exception as err:
                tries += 1

        if tries == 3:
            self.logger.error(f'Failed to communicate with device ({device_id}) to get recorded file')
