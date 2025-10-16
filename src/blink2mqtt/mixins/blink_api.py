# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from aiohttp import ClientSession
import asyncio
from asyncio import timeout
import base64
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink
from blinkpy.helpers.util import json_load
from datetime import datetime
import os


class BlinkAPIMixin(object):
    def increase_api_calls(self):
        if not self.last_call_date or self.last_call_date != str(datetime.now()):
            self.reset_api_call_count()
        self.api_calls += 1

    def reset_api_call_count(self):
        self.api_calls = 0
        self.last_call_date = str(datetime.now())
        self.logger.debug("Reset api call count for new day")

    def get_api_calls(self):
        return self.api_calls

    def get_last_call_date(self):
        return self.last_call_date

    def is_rate_limited(self):
        return self.rate_limited

    async def connect(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = ClientSession()
        self.blink = Blink(session=self.session)

        cred_path = os.path.join(self.config["config_path"], "blink.cred")
        key_path = os.path.join(self.config["config_path"], "key.txt")

        # if cred file exists, lets try it
        auth = None
        if os.path.exists(cred_path):
            self.logger.info("Prior credential file found, trying those credentials")
            auth = Auth(await json_load(cred_path), no_prompt=True)
        else:
            self.logger.info(
                "Prior credential file not found, trying simple name/password"
            )
            auth = Auth(
                {
                    "username": self.blink_config["username"],
                    "password": self.blink_config["password"],
                },
                no_prompt=True,
            )

        self.blink.auth = auth

        try:
            await self.blink.start()
        except BlinkTwoFARequiredError:
            self.logger.warning(
                "The 2fa key that Blink sends you will be needed. Save the key as filename key.txt in your config directory and I will wait up to 10 minutes for you to do this."
            )
            for _ in range(1200):
                if os.path.exists(key_path):
                    self.logger.info(
                        "I see the key.txt file, sending the key to Blink and deleting that file"
                    )
                    key = self.read_file(key_path).strip()
                    try:
                        os.remove(key_path)
                        await self.blink.send_2fa_code(key)
                        await self.blink.setup_post_verify()
                        await self.blink.save(cred_path)
                        await self.blink.refresh(force=True)
                    except Exception as err:
                        raise SystemError(f"Failed auth using key.txt file: {err}")
                    return
                await asyncio.sleep(1)

            self.logger.error(
                "I did not see the key.txt file in time. Please try again"
            )
            if os.path.exists(cred_path):
                os.remove(cred_path)
            key_path = os.path.join(self.config["config_path"], "key.txt")
            if os.path.exists(key_path):
                os.remove(key_path)
                raise SystemExit(1)

        await self.blink.refresh(force=True)
        await self.blink.save(cred_path)

    async def disconnect(self):
        cred_path = os.path.join(self.config["config_path"], "blink.cred")
        await self.blink.save(cred_path)
        if self.blink and hasattr(self.blink, "close"):
            await self.blink.close()
        await self.session.close()

    async def blink_refresh(self):
        await self.blink.refresh(force=True)

    async def get_cameras(self):
        for name, camera in self.blink.cameras.items():
            attributes = camera.attributes
            self.blink_cameras[attributes["serial"]] = {
                "config": {
                    "name": name,
                    "serial_number": attributes["serial"],
                    "camera_id": attributes["camera_id"],
                    "device_name": attributes["name"],
                    "device_type": attributes["type"],
                    "vendor": "Amazon",
                    "software_version": attributes["version"],
                    "motion": attributes["motion_detected"],
                    "motion_detection": attributes["motion_enabled"],
                    "temperature": attributes["temperature"],
                    "battery": attributes["battery"],
                    "wifi_strength": attributes["wifi_strength"],
                    "battery_level": attributes["battery_level"],
                    "battery_voltage": attributes["battery_voltage"],
                    "sync_module": attributes["sync_module"],
                    "sync_signal_strength": attributes["sync_signal_strength"],
                    "thumbnail": attributes["thumbnail"],
                    "video": attributes["video"],
                    "recent_clips": attributes["recent_clips"],
                    # "network_id": attributes["network_id"],
                    # "last_record": attributes["last_record"],
                }
            }

        return self.blink_cameras

    async def get_sync_modules(self):
        for _, sync_module in self.blink.sync.items():
            await sync_module.get_network_info()
            attributes = sync_module.attributes
            self.blink_sync_modules[attributes["serial"]] = {
                "config": {
                    "device_name": attributes["name"],
                    "device_type": "sync_module",
                    "serial_number": attributes["serial"],
                    "software_version": attributes["version"],
                    "vendor": "Amazon",
                    "arm_mode": sync_module.arm,
                    "region_id": attributes["region_id"],
                    "network_id": attributes["network_id"],
                    "host": sync_module.host,
                    "status": attributes["status"],
                    "sync_id": sync_module.sync_id,
                    "summary": sync_module.summary,
                    "motion_interval": sync_module.motion_interval,
                    "last_records": sync_module.last_records,
                    "local_storage": attributes["local_storage"],
                }
            }

        return self.blink_sync_modules

    # Arm mode  -----------------------------------------------------------------------------------

    async def set_arm_mode(self, device_id, switch):
        if device_id in self.blink_cameras:
            name = self.blink_cameras[device_id]["config"]["device_name"]
            device = self.blink.cameras[name]
        else:
            name = self.blink_sync_modules[device_id]["config"]["device_name"]
            device = self.blink.sync[name]

        try:
            async with timeout(5):
                response = await device.async_arm(switch)
                self.logger.info(f"Set arm mode for {device_id}: {response}")
                return response
        except asyncio.TimeoutError:
            self.logger.error(f"[set_arm_mode] Request time out for {device_id}")
        except Exception as e:
            self.logger.error(f"[set_arm_mode] Failed for {device_id}: {e}")

    # Motion --------------------------------------------------------------------------------------

    def get_camera_motion(self, device_id):

        try:
            device = self.blink_cameras.get(device_id)
            name = device["config"]["device_name"]
            motion = device.sync.motion[name]
            device["config"]["motion"] = motion
        except Exception:
            self.logger.error(f"[get_motion] Failed for {device_id}", exc_info=True)

        return motion

    def set_motion_detection(self, device_id, switch):

        try:
            device = self.blink_cameras.get(device_id)
            camera = self.blink.cameras.get(device["config"]["name"])
            response = camera.set_motion_detection(switch)
        except Exception as e:
            self.logger.error(f"[set_motion] Failed for {device_id}: {e}")
            return

        return response

    # Snapshots -----------------------------------------------------------------------------------

    async def take_snapshot_from_device(self, device_id):

        try:
            device = self.blink_cameras.get(device_id)
            camera = self.blink.cameras.get(device["config"]["name"])
            await camera.snap_picture()
            await asyncio.sleep(3)  # Blink says to give them 2-5 seconds
        except Exception as e:
            self.logger.error(
                f"[take_snapshot] Failed to take snapshot for {device_id}: {e}"
            )

    async def get_snapshot_from_device(self, device_id):

        try:
            device = self.blink_cameras[device_id]
            camera = self.blink.cameras.get(device["config"]["name"])
            image = camera.image_from_cache
            if not image:
                self.logger.info(
                    f"[get_snapshot] Empty cache for {device_id}, skipping."
                )
                return
            encoded = base64.b64encode(image).decode("utf-8")
        except Exception as e:
            self.logger.error(
                f"[get_snapshot_from_device] Failed to take snapshot for {device_id}: {e}"
            )
            return

        return encoded

    # Recorded file -------------------------------------------------------------------------------
    def get_recorded_file(self, device_id, file):
        device = self.blink_cameras.get(device_id)
        camera = self.blink.cameras.get(device["config"]["name"])

        tries = 0
        while tries < 3:
            try:
                data_raw = camera.download_file(file)
                if data_raw:
                    data_base64 = base64.b64encode(data_raw).decode("utf-8")
                    self.logger.info(
                        f"[recording] Processed recording from ({device_id}) {len(data_raw)} bytes raw, and {len(data_base64)} bytes base64"
                    )
                    if len(data_base64) >= 100 * 1024 * 1024:
                        self.logger.error(
                            "[recording] Skipping oversized recording (>100 MB)"
                        )
                        return
                    return data_base64
            except Exception as err:
                tries += 1
                self.logger.warning(
                    f"[recording] Retry {tries}/3 downloading recording from {device_id}: {err}"
                )

        if tries == 3:
            self.logger.error(
                f"[recording] Failed after 3 attempts for {device_id}", exc_info=True
            )
