#!/usr/bin/env python3

import argparse
import json
import logging
import math
import os
import requests
import sys

from dotenv import load_dotenv
from libdyson.dyson_pure_cool import DysonPureCool
from libdyson.exceptions import (
    DysonConnectionRefused,
    DysonConnectTimeout,
    DysonInvalidCredential,
    DysonNotConnected,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATE_FILE = 'state.json'

def save_state(state):
    with open(STATE_FILE, 'w') as file_handle:
        json.dump(state, file_handle)


def load_state():
    try:
        with open(STATE_FILE, 'r') as file_handle:
            return json.load(file_handle)
    except FileNotFoundError:
        return {}


def send_pushover_alert(title, message):
    logger.info(f"Sending Pushover alert (title: '{title}')")
    try:
        req = requests.post("https://api.pushover.net/1/messages.json", data={
            "token":   os.environ.get('PUSHOVER_APP_TOKEN'),
            "user":    os.environ.get('PUSHOVER_USER_TOKEN'),
            "title":   title,
            "message": message
        })
        req.raise_for_status()
    except requests.exceptions.HTTPError as err:
        logger.error(f"HTTP error when sending alert! Error: {err}")
        sys.exit(1)
    except requests.exceptions.ConnectionError as err:
        logger.error(f"Connection error when sending alert! Error: {err}")
        sys.exit(1)
    except requests.exceptions.Timeout as err:
        logger.error(f"Timeout error when sending alert! Error: {err}")
        sys.exit(1)
    except requests.exceptions.RequestException as err:
        logger.error(f"Request error when sending alert! Error: {err}")
        sys.exit(1)


def main():

    # Load environment variables from '.env'
    load_dotenv()

    # Retrieve our alert thresholds from the command-line parameters
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-humidity',
                        dest='max_humidity',
                        type=int,
                        help='The humidity alert threshold.')
    args = parser.parse_args()

    # Make sure the user has provided at least one alerting threshold
    if args.max_humidity is None:
        logger.error("You must provide at least one alerting threshold!")
        sys.exit(1)

    # Check we have the required credentials and connection info
    if not os.environ.get('DYSON_SERIAL') or \
       not os.environ.get('DYSON_CREDENTIAL') or \
       not os.environ.get('DYSON_DEVICE_TYPE') or \
       not os.environ.get('DYSON_HOST') or \
       not os.environ.get('PUSHOVER_APP_TOKEN') or \
       not os.environ.get('PUSHOVER_USER_TOKEN'):
        logger.info("Environment variables not set! Please make sure "
            "DYSON_SERIAL, DYSON_CREDENTIAL, DYSON_DEVICE_TYPE, DYSON_HOST, "
            "PUSHOVER_APP_TOKEN and PUSHOVER_USER_TOKEN are set.")
        sys.exit(1)

    # Connect to the device
    device = DysonPureCool(os.environ.get('DYSON_SERIAL'),
                           os.environ.get('DYSON_CREDENTIAL'),
                           os.environ.get('DYSON_DEVICE_TYPE'))
    try:
        device.connect(os.environ.get('DYSON_HOST'))
    except DysonInvalidCredential:
        logger.error("Invalid device credentials provided!")
        sys.exit(1)
    except DysonConnectionRefused:
        logger.error("Connection refused by target device.")
        sys.exit(1)
    except DysonConnectTimeout:
        logger.error("Connection timed out.")
        sys.exit(1)
    except DysonNotConnected:
        logger.error("Device is not connected.")
        sys.exit(1)
    except Exception as err:
        logger.error(f"An unexpected exception occurred: {err}")
        sys.exit(1)

    # Retrieve and print some information from the device
    logger.info(f"PM2.5:     {device.particulate_matter_2_5}")
    logger.info(f"PM10:      {device.particulate_matter_10}")
    logger.info(f"VOC:       {device.volatile_organic_compounds}")
    logger.info(f"NO2:       {device.nitrogen_dioxide}")
    logger.info(f"Temp:      {device.temperature}")
    logger.info(f"Humidity:  {device.humidity}")

    # Load previous state
    state = load_state()
    last_humidity = state.get('last_humidity')
    logger.info(f"Previous humidity reading was: {last_humidity}%")

    # Check the device values against our alert criteria
    if args.max_humidity is not None:
        if device.humidity >= args.max_humidity:
            # No prev. reading or prev. reading was safe but now isn't
            if last_humidity is None or last_humidity <= args.max_humidity:
                send_pushover_alert("Rel. humidity above threshold",
                    f"Humidity is: {device.humidity}%")

        # Prev. reading was above threshold but has returned to OK
        if device.humidity < args.max_humidity and \
           last_humidity > args.max_humidity:
            send_pushover_alert("Rel. humidity OK",
                f"Humidity returned to OK value ({device.humidity}%)")

    state['last_humidity'] = device.humidity
    save_state(state)

    logger.info("Done!")


if __name__ == "__main__":
    main()
