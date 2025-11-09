# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Jeff Culverhouse
from aiohttp import ClientSession
import asyncio
from asyncio import timeout
import base64
from blinkpy.auth import Auth, BlinkTwoFARequiredError, UnauthorizedError
from blinkpy.blinkpy import Blink
from blinkpy.helpers.util import json_load
from datetime import datetime
import inspect
import json
import os

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from blink2mqtt.interface import BlinkServiceProtocol as Blink2Mqtt


class BlinkAPIMixin(object):
    def increase_api_calls(self: Blink2Mqtt) -> None:
        if not self.last_call_date or self.last_call_date != str(datetime.now()):
            self.reset_api_call_count()
        self.api_calls += 1

    def reset_api_call_count(self: Blink2Mqtt) -> None:
        self.api_calls = 0
        self.last_call_date = str(datetime.now())
        self.logger.debug("Reset api call count for new day")

    def get_api_calls(self: Blink2Mqtt) -> int:
        return self.api_calls

    def get_last_call_date(self: Blink2Mqtt) -> str:
        return self.last_call_date

    def is_rate_limited(self: Blink2Mqtt) -> bool:
        return self.rate_limited

    async def connect(self: Blink2Mqtt) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

        self.session = ClientSession()
        self.blink = Blink(session=self.session)

        cred_path = os.path.join(self.config["config_path"], "blink.cred")
        key_path = os.path.join(self.config["config_path"], "key.txt")

        # --- Choose credential source ---
        auth: Auth | None = None
        if os.path.exists(cred_path):
            self.logger.info("Using existing Blink credentials")
            creds = await json_load(cred_path)
            auth = Auth(creds, no_prompt=True)
        elif self.blink_config.get("username") and self.blink_config.get("password"):
            self.logger.info("Using username/password from config")
            auth = Auth(
                {
                    "username": self.blink_config["username"],
                    "password": self.blink_config["password"],
                },
                no_prompt=True,
            )
        else:
            self.logger.error("No credentials found (no cred file, username, or password). Cannot authenticate.")
            raise SystemExit(1)

        self.blink.auth = auth

        # --- Attempt to start Blink connection ---
        try:
            await self.blink.start()
        except UnauthorizedError:
            self.logger.error("Stored credentials invalid — deleting and exiting")
            await asyncio.to_thread(os.remove, cred_path)
            raise SystemExit(1)

        except BlinkTwoFARequiredError:
            self.logger.warning("2FA required — place the Blink key in key.txt in your config directory. Waiting up to 10 minutes...")

            async def wait_for_key_file(timeout: int = 600) -> str | None:
                """Poll for the presence of key.txt asynchronously."""
                for _ in range(timeout):
                    if os.path.exists(key_path):
                        return await asyncio.to_thread(self.read_file, key_path)
                    await asyncio.sleep(1)
                return None

            key = await wait_for_key_file()
            if not key:
                self.logger.error("2FA key file not found in time. Cleaning up and aborting.")
                await asyncio.gather(*[asyncio.to_thread(os.remove, p) for p in (cred_path, key_path) if os.path.exists(p)])
                raise SystemExit(1)

            self.logger.info("Found key.txt, completing 2FA process")
            try:
                await asyncio.to_thread(os.remove, key_path)
                await self.blink.send_2fa_code(key)
                await self.blink.setup_post_verify()
                await self.blink.save(cred_path)
                await self.blink.refresh()
                return
            except Exception as err:
                raise SystemError(f"Failed to complete 2FA auth: {err}")

        # --- Normal successful auth path ---
        await self.blink.refresh()
        await self.blink.save(cred_path)

    async def disconnect(self: Blink2Mqtt) -> None:
        cred_path = os.path.join(self.config["config_path"], "blink.cred")
        await self.blink.save(cred_path)
        if self.session:
            await self.session.close()

    async def blink_refresh(self: Blink2Mqtt) -> None:
        try:
            await self.blink.refresh()
        except AttributeError as e:
            self.logger.error(f"Blink failed a 'refresh' command: {e}")
            pass

    async def get_cameras(self: Blink2Mqtt) -> dict[str, Any]:
        for name, camera in self.blink.cameras.items():
            attributes = camera.attributes
            self.blink_cameras[attributes["serial"]] = {
                "config": {
                    "name": name,
                    "serial_number": attributes["serial"],
                    "camera_id": int(attributes["camera_id"]),
                    "device_name": attributes["name"],
                    "device_type": attributes["type"],
                    "vendor": "Amazon",
                    "software_version": attributes["version"],
                    "motion": attributes["motion_detected"],
                    "motion_detection": attributes["motion_enabled"],
                    "supports_get_config": attributes["type"] in {"owl", "catalina"},
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
                }
            }
        return self.blink_cameras

    async def get_sync_modules(self: Blink2Mqtt) -> dict[str, Any]:
        for _, sync_module in self.blink.sync.items():
            await sync_module.get_network_info()
            self.logger.info(f"SYNC MOD NETWORK INFO: {json.dumps(sync_module.network_info)}")
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

    async def handle_blink_response(self: Blink2Mqtt, response: str | dict[str, Any]) -> bool | None:
        if response and isinstance(response, dict):
            if response.get("code", 200) == 307:
                self.logger.warning("Blink busy for device, retrying in 2s...")
                await asyncio.sleep(2)
                return None
            if response.get("state_stage") in {"completed", "rest"}:
                return True
        self.logger.warning(f"failed command to blink device, response: {json.dumps(response)}")
        return False

    # Arm mode  -----------------------------------------------------------------------------------

    async def set_arm_mode(self: Blink2Mqtt, device_id: str, switch: bool) -> Any | None:
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
            return None
        except Exception as e:
            self.logger.error(f"[set_arm_mode] Failed for {device_id}: {e}")
            return None

    # Nightvision ---------------------------------------------------------------------------------

    async def get_night_vision(self: Blink2Mqtt, device_id: str) -> str:
        device = self.blink_cameras[device_id]
        camera = self.blink.cameras[device["config"]["name"]]

        try:
            response = await camera.night_vision
            return response and str(response.get("illuminator_enable", ""))
            # {'night_vision_control': None, 'illuminator_enable': 'auto', 'illuminator_enable_v2': None}
        except asyncio.TimeoutError:
            self.logger.error(f"[get_night_vision] Request time out for {device_id}")
            return ""
        except Exception as e:
            self.logger.error(f"[get_night_vision] Failed for {device_id}: {e}")
            return ""

    async def set_night_vision(self: Blink2Mqtt, device_id: str, switch: str) -> bool | None:
        max_retries = 5
        base_delay = 2
        device = self.blink_cameras[device_id]
        camera = self.blink.cameras[device["config"]["name"]]

        for attempt in range(1, max_retries + 1):
            try:
                blink_response = await camera.async_set_night_vision(switch)
                result = await self.handle_blink_response(blink_response)
                if result is None:
                    continue
                return result
            except Exception as e:
                self.logger.error(
                    f"[set_night_vision] Exception on attempt {attempt} for {device_id}: {e}",
                    exc_info=True,
                )
                await asyncio.sleep(base_delay * attempt)

        self.logger.error(f"[set_night_vision] Failed for {device_id} after {max_retries} retries")
        return None

    # Motion --------------------------------------------------------------------------------------

    def get_camera_motion(self: Blink2Mqtt, device_id: str) -> Any | None:
        try:
            name = self.blink_cameras[device_id]["config"]["device_name"]
            device = self.blink.cameras[name]
            motion = device.sync.motion[name]
            device["config"]["motion"] = motion
        except Exception:
            self.logger.error(f"[get_motion] Failed for {device_id}", exc_info=True)

        return motion

    async def set_motion_detection(self: Blink2Mqtt, device_id: str, switch: bool) -> bool | None:
        max_retries = 5

        for attempt in range(1, max_retries + 1):
            try:
                if device_id in self.blink_cameras:
                    device = self.blink_cameras[device_id]
                    camera = self.blink.cameras[device["config"]["name"]]
                    self.logger.info(f"calling async_arm({switch}) to camera {device_id}: {inspect.iscoroutinefunction(camera.async_arm)}")
                    blink_response = await camera.async_arm(switch)
                    result = await self.handle_blink_response(blink_response)
                    if result is None:
                        continue
                    return result

                elif device_id in self.blink_sync_modules:
                    device = self.blink_sync_modules[device_id]
                    sync_module = self.blink.sync[device["device_name"]]
                    self.logger.info(f"calling async_arm({switch}) to sync_module {device_id}: {inspect.iscoroutinefunction(camera.async_arm)}")
                    blink_response = await sync_module.async_arm(switch)
                    result = await self.handle_blink_response(blink_response)
                    if result is None:
                        continue
                    return result

                else:
                    self.logger.error(f"[set_motion] Unknown device id: {device_id}")
                    return None

            except Exception as e:
                self.logger.error(
                    f"[set_motion_detection] Exception on attempt {attempt} for {device_id}: {e}",
                    exc_info=True,
                )
                await asyncio.sleep(2 * attempt)

        self.logger.error(f"[set_motion] Failed for {device_id} after {max_retries} retries")
        return None

    # Snapshots -----------------------------------------------------------------------------------

    async def take_snapshot_from_device(self: Blink2Mqtt, device_id: str) -> None:

        try:
            device = self.blink_cameras[device_id]
            camera = self.blink.cameras[device["config"]["name"]]
            await camera.snap_picture()
            await asyncio.sleep(3)  # Blink says to give them 2-5 seconds
        except Exception as e:
            self.logger.error(f"[take_snapshot] Failed to take snapshot for {device_id}: {e}")

    async def get_snapshot_from_device(self: Blink2Mqtt, device_id: str) -> str | None:

        try:
            device = self.blink_cameras[device_id]
            camera = self.blink.cameras[device["config"]["name"]]
            image = camera.image_from_cache
            if not image:
                self.logger.info(f"[get_snapshot] Empty cache for {device_id}, skipping.")
                return None
            encoded = base64.b64encode(image).decode("utf-8")
            return encoded
        except Exception as e:
            self.logger.error(f"[get_snapshot_from_device] Failed to take snapshot for {device_id}: {e}")
            return None

    # Recorded file -------------------------------------------------------------------------------
    def get_recorded_file(self: Blink2Mqtt, device_id: str, file: str) -> str | None:
        device = self.blink_cameras[device_id]
        camera = self.blink.cameras[device["config"]["name"]]

        tries = 0
        while tries < 3:
            try:
                data_raw = camera.download_file(file)
                if data_raw:
                    data_base64 = base64.b64encode(data_raw).decode("utf-8")
                    self.logger.info(f"[recording] Processed recording from ({device_id}) {len(data_raw)} bytes raw, and {len(data_base64)} bytes base64")
                    if len(data_base64) >= 100 * 1024 * 1024:
                        self.logger.error("[recording] Skipping oversized recording (>100 MB)")
                        return None
                    return data_base64
            except Exception as err:
                tries += 1
                self.logger.warning(f"[recording] Retry {tries}/3 downloading recording from {device_id}: {err}")

        if tries == 3:
            self.logger.error(f"[recording] Failed after 3 attempts for {device_id}", exc_info=True)
        return None

    # collect/process blink events ----------------------------------------------------------------

    async def collect_all_blink_events(self: Blink2Mqtt) -> None:
        tasks = [self.get_events_from_device(device_id) for device_id in self.blink_sync_modules]

        await asyncio.gather(*tasks)

    async def get_events_from_device(self: Blink2Mqtt, device_id: str) -> None:
        blink_device = self.blink_sync_modules[device_id]
        sync_module = self.blink.sync.get(blink_device["config"]["device_name"], None)
        if not sync_module:
            self.logger.error(f"Tried to get events from unknown sync_module {device_id}")
            return

        tries = 0
        while tries < 3:
            try:
                event = await sync_module.get_events()
                if not event:
                    self.logger.info("No more events waiting...")
                    break
                self.logger.info(f"Got event: {json.dumps(event)}")
                # await self.queue_device_event(device_id, code, payload)
            except Exception as err:
                tries += 1
                self.logger.warning(f"[events] Retry {tries}/3 checking for events from {device_id}: {err}")
        if tries == 3:
            self.logger.error(f"[events] Failed to communicate for events for device ({device_id})")

    async def queue_device_event(self: Blink2Mqtt, device_id: str, code: str, payload: Any) -> None:
        self.logger.info(f"queue_device_event for {device_id}, code {code}, payload {json.dumps(payload)}")
        device = self.blink_cameras[device_id]
        config = device["config"]
        try:
            if (code == "ProfileAlarmTransmit" and config["is_ad110"]) or (code == "VideoMotion" and not config["is_ad110"]):
                motion_payload = {"state": "on" if payload["action"] == "Start" else "off", "region": ", ".join(payload["data"]["RegionName"])}
                self.events.append({"device_id": device_id, "event": "motion", "payload": motion_payload})
            elif code == "CrossRegionDetection" and payload["data"]["ObjectType"] == "Human":
                human_payload = "on" if payload["action"] == "Start" else "off"
                self.events.append({"device_id": device_id, "event": "human", "payload": human_payload})
            elif code == "_DoTalkAction_":
                doorbell_payload = "on" if payload["data"]["Action"] == "Invite" else "off"
                self.events.append({"device_id": device_id, "event": "doorbell", "payload": doorbell_payload})
            elif code == "NewFile":
                if (
                    "File" in payload["data"]
                    and "[R]" not in payload["data"]["File"]
                    and ("StoragePoint" not in payload["data"] or payload["data"]["StoragePoint"] != "Temporary")
                ):
                    file_payload = {"file": payload["data"]["File"], "size": payload["data"]["Size"]}
                    self.events.append({"device_id": device_id, "event": "recording", "payload": file_payload})
            elif code == "LensMaskOpen":
                device["privacy_mode"] = True
                self.events.append({"device_id": device_id, "event": "privacy_mode", "payload": "on"})
            elif code == "LensMaskClose":
                device["privacy_mode"] = False
                self.events.append({"device_id": device_id, "event": "privacy_mode", "payload": "off"})
            # lets send these but not bother logging them here
            elif code == "TimeChange":
                self.events.append({"device_id": device_id, "event": code, "payload": payload["action"]})
            elif code == "NTPAdjustTime":
                self.events.append({"device_id": device_id, "event": code, "payload": payload["action"]})
            elif code == "RtspSessionDisconnect":
                self.events.append({"device_id": device_id, "event": code, "payload": payload["action"]})
            # lets just ignore these
            elif code == "InterVideoAccess":  # I think this is US, accessing the API of the camera, lets not inception!
                pass
            elif code == "VideoMotionInfo":
                pass
            # save everything else as a 'generic' event
            else:
                self.logger.debug(f"Event on {device_id} - {code}: {payload}")
                self.events.append({"device_id": device_id, "event": code, "payload": payload})
        except Exception as err:
            self.logger.error(f"[queue_device_event] Failed to understand event from {device_id}: {err}", exc_info=True)

    def get_next_event(self: Blink2Mqtt) -> dict[str, Any] | None:
        return self.events.pop(0) if len(self.events) > 0 else None

    async def process_events(self: Blink2Mqtt) -> None:
        try:
            while device_event := self.get_next_event():
                if "device_id" not in device_event:
                    self.logger.debug(f"[process_events] Got event but it's missing a device_id: {device_event}")
                    continue

                device_id = device_event["device_id"]
                event = device_event["event"]
                payload = device_event["payload"]
                states = self.states.get(device_id, None)
                if not states:
                    self.logger.debug(f"[process_events] Got event for device_id we don't know: {device_event}")
                    continue

                # if one of our known sensors
                if event in ["motion", "human", "doorbell", "recording", "privacy_mode"]:
                    if event == "recording" and payload["file"].endswith(".jpg"):
                        image = self.get_recorded_file(device_id, payload["file"])
                        # only store and send to MQTT if we got an image AND the image has changed
                        if image and (states["eventshot"] is None or states["eventshot"] != image):
                            states["eventshot"] = image
                            await self.publish_device_image(device_id, "eventshot")
                    else:
                        # only log details if not a recording
                        if event != "recording":
                            self.logger.debug(f"Got event for {self.get_device_name(device_id)}: {event} - {payload}")
                        self.upsert_state(device_id, last_event=f"{event}: {json.dumps(payload)}", last_event_time=str(datetime.now()))

                    # other ways to infer "privacy mode" is off and needs updating
                    # if event in ['motion','human','doorbell'] and states['privacy_mode'] == 'on':
                    # states['privacy_mode'] = 'off'
                else:
                    self.logger.debug(f'Got {{{event}: {payload}}} for "{self.get_device_name(device_id)}"')
                    self.upsert_state(device_id, last_event=f"{event}: {json.dumps(payload)}", last_event_time=str(datetime.now()))

                await self.publish_device_state(device_id)
        except Exception as err:
            self.logger.error(f"[process_events] Failed trying to process event: {err}", exc_info=True)
