# This software is licensed under the MIT License, which allows you to use,
# copy, modify, merge, publish, distribute, and sell copies of the software,
# with the requirement to include the original copyright notice and this
# permission notice in all copies or substantial portions of the software.
#
# The software is provided 'as is', without any warranty.

import asyncio
import argparse
from blink_mqtt import BlinkMqtt
import logging
import os
import sys
import time
from util import *
import yaml

# Let's go!
version = read_version()

# Cmd-line args
argparser = argparse.ArgumentParser()
argparser.add_argument(
    '-c',
    '--config',
    required=False,
    help='Directory holding config.yaml or full path to config file',
)
args = argparser.parse_args()

# Setup config from yaml file or env
configpath = args.config or '/config'
try:
    if not configpath.endswith('.yaml'):
        if not configpath.endswith('/'):
            configpath += '/'
        configfile = configpath + 'config.yaml'
    with open(configfile) as file:
        config = yaml.safe_load(file)
    config['config_path'] = configpath
    config['config_from'] = 'file'
except:
    config = {
        'mqtt': {
            'host': os.getenv('MQTT_HOST') or 'localhost',
            'qos': int(os.getenv('MQTT_QOS') or 0),
            'port': int(os.getenv('MQTT_PORT') or 1883),
            'username': os.getenv('MQTT_USERNAME'),
            'password': os.getenv('MQTT_PASSWORD'),  # can be None
            'tls_enabled': os.getenv('MQTT_TLS_ENABLED') == 'true',
            'tls_ca_cert': os.getenv('MQTT_TLS_CA_CERT'),
            'tls_cert': os.getenv('MQTT_TLS_CERT'),
            'tls_key': os.getenv('MQTT_TLS_KEY'),
            'prefix': os.getenv('MQTT_PREFIX') or 'blink2mqtt',
            'homeassistant': os.getenv('MQTT_HOMEASSISTANT') == True,
            'discovery_prefix': os.getenv('MQTT_DISCOVERY_PREFIX') or 'homeassistant',
        },
        'blink': {
            'hosts': os.getenv("BLINK_HOSTS"),
            'names': os.getenv("BLINK_NAMES"),
            'port': int(os.getenv("BLINK_PORT") or 80),
            'username': os.getenv("BLINK_USERNAME") or "admin",
            'password': os.getenv("BLINK_PASSWORD"),
            'storage_update_interval': int(os.getenv("STORAGE_UPDATE_INTERVAL") or 900),
            'snapshot_update_interval': int(os.getenv("SNAPSHOT_UPDATE_INTERVAL") or 300),
        },
        'debug': True if os.getenv('DEBUG') else False,
        'hide_ts': True if os.getenv('HIDE_TS') else False,
        'timezone': os.getenv('TZ'),
        'config_from': 'env',
    }
config['version'] = version
config['configpath'] = os.path.dirname(configpath)

# defaults
if 'username' not in config['mqtt']: config['mqtt']['username'] = ''
if 'password' not in config['mqtt']: config['mqtt']['password'] = ''
if 'qos'      not in config['mqtt']: config['mqtt']['qos'] = 0
if 'timezone' not in config:         config['timezone'] = 'UTC'
if 'debug'    not in config:         config['debug'] = os.getenv('DEBUG') or False
if 'hide_ts'  not in config:         config['hide_ts'] = os.getenv('HIDE_TS') or False

# init logging, based on config settings
logging.basicConfig(
    format = '%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s' if config['hide_ts'] == False else '[%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO if config['debug'] == False else logging.DEBUG
)
logger = logging.getLogger(__name__)
logger.info(f'Starting: blink2mqtt v{version}')
logger.info(f'Config loaded from {config["config_from"]}')

# Check for required config properties
if config['blink']['hosts'] is None:
    logger.error('Missing env var: BLINK_HOSTS or blink.hosts in config')
    exit(1)
config['blink']['host_count'] = len(config['blink']['hosts'])

if config['blink']['names'] is None:
    logger.error('Missing env var: BLINK_NAMES or blink.names in config')
    exit(1)
config['blink']['name_count'] = len(config['blink']['names'])

if config['blink']['host_count'] != config['blink']['name_count']:
    logger.error('The BLINK_HOSTS and BLINK_NAMES must have the same number of space-delimited hosts/names')
    exit(1)
logger.info(f'Found {config["blink"]["host_count"]} host(s) defined to monitor')

if 'webrtc' in config['blink']:
    webrtc = config['blink']['webrtc']
    if 'host' not in webrtc:
        logger.error('Missing HOST in webrtc config')
        exit(1)
    if 'sources' not in webrtc:
        logger.error('Missing SOURCES in webrtc config')
        exit(1)
    config['blink']['webrtc_sources_count'] = len(config['blink']['webrtc']['sources'])
    if config['blink']['host_count'] != config['blink']['webrtc_sources_count']:
        logger.error('The BLINK_HOSTS and BLINK_WEBRTC_SOURCES must have the same number of space-delimited hosts/names')
        exit(1)
    if 'port' not in webrtc: webrtc['port'] = 1984
    if 'link' not in webrtc: webrtc['link'] = 'stream.html'

if config['blink']['password'] is None:
    logger.error('Please set the BLINK_PASSWORD environment variable')
    exit(1)

logger.debug("DEBUG logging is ON")

# Go!
with BlinkMqtt(config) as mqtt:
    asyncio.run(mqtt.main_loop())