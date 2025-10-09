# This software is licensed under the MIT License, which allows you to use,
# copy, modify, merge, publish, distribute, and sell copies of the software,
# with the requirement to include the original copyright notice and this
# permission notice in all copies or substantial portions of the software.
#
# The software is provided 'as is', without any warranty.

import asyncio
import argparse
import logging
import sys
from blink_mqtt import BlinkMqtt
from util import read_version, load_config

# Cmd-line args
argparser = argparse.ArgumentParser(description="Blink2MQTT bridge service")
argparser.add_argument(
    "-c", "--config",
    required=False,
    help="Directory holding config.yaml or full path to config file",
)
args = argparser.parse_args()

# Version + Config
version = read_version()
config_path = args.config or "/config/config.yaml"
config = load_config(config_path)
config["version"] = version

# Logging
log_format = (
    "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s"
    if not config["hide_ts"]
    else "[%(levelname)s] %(name)s: %(message)s"
)
logging.basicConfig(
    format=log_format,
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG if config["debug"] else logging.INFO,
)
logger = logging.getLogger(__name__)
logger.info(f"Starting blink2mqtt {version}")
logger.info(f"Config loaded from {config['config_from']}")

# Go
try:
    with BlinkMqtt(config) as mqtt:
        asyncio.run(mqtt.main_loop())
except KeyboardInterrupt:
    logger.warning("Interrupted by user, shutting down...")
    sys.exit(0)
except Exception as e:
    logger.exception(f"Fatal error in main loop: {e}")
    sys.exit(1)
