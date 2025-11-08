# This software is licensed under the MIT License, which allows you to use,
# copy, modify, merge, publish, distribute, and sell copies of the software,
# with the requirement to include the original copyright notice and this
# permission notice in all copies or substantial portions of the software.
#
# The software is provided 'as is', without any warranty.
import asyncio
import argparse
from json_logging import setup_logging, get_logger
from .core import Blink2Mqtt
from .mixins.helpers import ConfigError
from .mixins.mqtt import MqttError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="blink2mqtt", exit_on_error=True)
    p.add_argument(
        "-c",
        "--config",
        help="Directory or file path for config.yaml (defaults to /config/config.yaml)",
    )
    return p


async def async_main() -> int:
    setup_logging()
    logger = get_logger(__name__)

    parser = build_parser()
    args = parser.parse_args()

    try:
        async with Blink2Mqtt(args=args) as blink2mqtt:
            await blink2mqtt.main_loop()
    except ConfigError as err:
        logger.error(f"Fatal config error was found: {err}")
        return 1
    except MqttError as err:
        logger.error(f"MQTT service problems: {err}")
        return 1
    except KeyboardInterrupt:
        logger.warning("Shutdown requested (Ctrl+C). Exiting gracefully...")
        return 1
    except asyncio.CancelledError:
        logger.warning("Main loop cancelled.")
        return 1
    except Exception as err:
        logger.error(f"Unhandled exception: {err}", exc_info=True)
        return 1
    finally:
        logger.info("amcrest2mqtt stopped.")

    return 0


def main() -> int:
    try:
        return asyncio.run(async_main())
    except RuntimeError as err:
        # Fallback for nested loops (Jupyter, tests, etc.)
        if "asyncio.run() cannot be called from a running event loop" in str(err):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_main())
        raise
