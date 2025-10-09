# This software is licensed under the MIT License, which allows you to use,
# copy, modify, merge, publish, distribute, and sell copies of the software,
# with the requirement to include the original copyright notice and this
# permission notice in all copies or substantial portions of the software.
#
# The software is provided 'as is', without any warranty.

from aiohttp import ClientSession
import asyncio
from asyncio import timeout
from blinkpy.auth import Auth
from blinkpy.blinkpy import Blink
from blinkpy.helpers.util import json_load
import base64
import logging
import os
from util import *

class BlinkAPI(object):
    def __init__(self, config):
        self.logger = logging.getLogger(__name__)

        # we don't want to get this mess of deeper-level logging
        logging.getLogger("blinkpy.blinkpy").setLevel(logging.WARNING)
        logging.getLogger("blinkpy.sync_module").setLevel(logging.WARNING)

        self.blink_config = config['blink']
        self.config_path = os.path.join(config['config_path'], '')
        self.timezone = config['timezone']

        self.session = None
        self.blinkc = None

        self.last_call_date = ''
        self.devices = {}
        self.sync_modules = {}
        self.events = []

        self.sem = asyncio.Semaphore(4)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.disconnect()

    async def connect(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = ClientSession()
        self.blinkc = Blink(session=self.session)

        need2fa = False
        cred_path = os.path.join(self.config_path, 'blinkc.cred')
        if os.path.exists(cred_path):
            auth = Auth(await json_load(cred_path), no_prompt=True)
            if auth.login_attributes["token"] is None:
                self.logger.error('Failed to auth with credential file. Removing bad file and retrying')
                os.remove(cred_path)
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
            self.logger.warning('The 2fa key from Blink will be needed. Save the key as filename key.txt in your config directory and I will wait up to 5 minutes for you to do this.')
            for _ in range(600):
                key_path = os.path.join(self.config_path, 'key.txt')
                if os.path.exists(key_path):
                    self.logger.info('I see the key.txt file, sending the key to Blink and deleting that file')
                    key = read_file(key_path).strip()
                    await auth.send_auth_key(self.blinkc, key)
                    await self.blinkc.setup_post_verify()
                    try:
                        os.remove(key_path)
                    except Exception as err:
                        self.logger.error(f'Failed to delete key.txt file: {err}')
                        pass
                    try:
                        await self.blinkc.save(cred_path)
                    except Exception as err:
                        self.logger.error(f'Failed to write credential file: {err}')
                        pass
                    return
                await asyncio.sleep(1)

            self.logger.error('I did not see the key.txt file in time. Please try again')
            cred_path = os.path.join(self.config_path, 'blinkc.cred')
            if os.path.exists(cred_path):
                os.remove(cred_path)
            key_path = os.path.join(self.config_path, 'key.txt')
            if os.path.exists(key_path):
                os.remove(key_path)
                raise SystemExit(1)

        # can we just go ahead and save this now?
        cred_path = os.path.join(self.config_path, 'blinkc.cred')
        await self.blinkc.save(cred_path)

    async def disconnect(self):
        cred_path = os.path.join(self.config_path, 'blinkc.cred')
        await self.blinkc.save(cred_path)
        if hasattr(self.blinkc, "close"):
            await self.blinkc.close()
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
        for _, sync_module in self.blinkc.sync.items():
            await sync_module.get_network_info()
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

    # Arm mode  -----------------------------------------------------------------------------------

    async def set_arm_mode(self, device_id, switch):
        if device_id in self.devices:
            name = self.devices[device_id]['config']['device_name']
            device = self.blinkc.cameras[name]
        else:
            name = self.sync_modules[device_id]['config']['device_name']
            device = self.blinkc.sync[name]

        try:
            async with timeout(5):
                response = await device.async_arm(switch)
                self.logger.info(f'Set arm mode for {device_id}: {response}')
                return response
        except asyncio.TimeoutError:
            return "Request timed out"
        except Exception:
            self.logger.error(f"[set_arm_mode] Failed for {device_id}", exc_info=True)

    # Motion --------------------------------------------------------------------------------------

    def get_camera_motion(self, device_id):
        name = self.devices[device_id]['config']['device_name']
        device = self.blinkc.cameras[name]

        try:
            motion = device.sync.motion[name]
            self.devices[device_id]['config']['motion'] = motion
        except Exception:
            self.logger.error(f"[get_motion] Failed for {device_id}", exc_info=True)

        return motion

    def set_motion_detection(self, device_id, switch):
        device = self.devices[device_id]

        try:
            response = device["camera"].set_motion_detection(switch)
        except Exception:
            self.logger.error(f"[set_motion] Failed for {device_id}", exc_info=True)

        return response

    # Snapshots -----------------------------------------------------------------------------------

    async def collect_all_device_snapshots(self):
        tasks = [self.take_snapshot_from_device(device_id) for device_id in self.devices]
        await asyncio.gather(*tasks, return_exceptions=True)

        try:
            async with timeout(10):
                await self.blinkc.refresh()
        except asyncio.TimeoutError:
            self.logger.warning("[refresh] Blink cloud refresh timed out after 10 s — continuing with cached data")

        tasks = [self.get_snapshot_from_device(device_id) for device_id in self.devices]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def take_snapshot_from_device(self, device_id):
        device = self.devices.get(device_id)
        if not device:
            self.logger.warning(f"[take_snapshot] Device {device_id} not found in self.devices, skipping snapshot.")
            return
        camera = self.blinkc.cameras.get(device['config']['device_name'])
        if not camera:
            self.logger.warning(f"[take_snapshot] Camera {device_id} not found in Blink object, skipping.")
            return

        async with self.sem:
            tries = 0
            while tries < 3:
                try:
                    await camera.snap_picture()
                    await asyncio.sleep(3) # Blink says to give them 2-5 seconds
                    break
                except Exception as err:
                    tries += 1
                    self.logger.warning(f"[take_snapshot] Retry {tries}/3 taking snapshot from {device_id}: {err}")

            if tries == 3:
                self.logger.error(f"[take_snapshot] Failed after 3 attempts for {device_id}", exc_info=True)

    async def get_snapshot_from_device(self, device_id):
        device = self.devices.get(device_id)
        if not device:
            self.logger.warning(f"[get_snapshot] Device {device_id} not found in self.devices, skipping snapshot.")
            return
        camera = self.blinkc.cameras.get(device['config']['device_name'])
        if not camera:
            self.logger.warning(f"[get_snapshot] Camera {device_id} not found in Blink object, skipping.")
            return

        async with self.sem:
            tries = 0
            while tries < 3:
                try:
                    image = camera.image_from_cache
                    if not image:
                        self.logger.debug(f"[get_snapshot] Empty cache for {device_id}, skipping.")
                        return
                    encoded = base64.b64encode(image).decode('utf-8')
                    if 'snapshot' not in device or device['snapshot'] != encoded:
                        device['snapshot'] = encoded
                        self.logger.info(f'[get_snapshot] Processed NEW snapshot from ({device_id}) {len(image)} bytes raw, and {len(encoded)} bytes base64')
                    break
                except Exception as err:
                    tries += 1
                    self.logger.warning(f"[get_snapshot] Retry {tries}/3 getting snapshot from {device_id}: {err}")

            if tries == 3:
                self.logger.error(f"[get_snapshot] Failed after 3 attempts for {device_id}", exc_info=True)

    async def get_snapshot(self, device_id):
        if 'snapshot' in self.devices[device_id]:
            return self.devices[device_id]['snapshot']
        return None

    # Recorded file -------------------------------------------------------------------------------
    def get_recorded_file(self, device_id, file):
        device = self.devices.get(device_id)
        if not device:
            self.logger.warning(f"[recording] Device {device_id} not found in self.devices, skipping recorded file.")
            return

        tries = 0
        while tries < 3:
            try:
                data_raw = device["camera"].download_file(file)
                if data_raw:
                    data_base64 = base64.b64encode(data_raw).decode('utf-8')
                    self.logger.info(f'[recording] Processed recording from ({device_id}) {len(data_raw)} bytes raw, and {len(data_base64)} bytes base64')
                    if len(data_base64) >= 100 * 1024 * 1024:
                        self.logger.error("[recording] Skipping oversized recording (>100 MB)")
                        return
                    return data_base64
            except Exception as err:
                tries += 1
                self.logger.warning(f"[recording] Retry {tries}/3 downloading recording from {device_id}: {err}")

        if tries == 3:
            self.logger.error(f"[recording] Failed after 3 attempts for {device_id}", exc_info=True)