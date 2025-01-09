"""AirPods Battery Monitor.

This module provides functionality to monitor the battery status of Apple AirPods devices.
It uses Bluetooth Low Energy (BLE) to scan for and connect to AirPods devices,
reading their battery and charging status.

Example:
    Basic usage with CLI::

        $ python airpods.py --json
        {
            "status": 1,
            "model": "AirPodsMax",
            "charge": {
                "left": 95,
                "right": 95,
                "case": null
            },
            "charging_left": false,
            "charging_right": false,
            "charging_case": null,
            "date": "2025-01-09 22:25:00"
        }
"""

import argparse
import asyncio
import logging
import traceback
from binascii import hexlify
from datetime import datetime
from json import dumps
from time import time_ns

from bleak import BleakScanner


class AirPodsMonitor:
    """
    Monitors AirPods battery and charging status using BLE.

    Attributes:
        AIRPODS_MANUFACTURER: Apple's manufacturer ID for BLE devices
        RECENT_BEACONS_MAX_T_NS: Maximum time to keep beacon data in nanoseconds
        MODEL_DATA_LENGTHS: Expected data lengths for different AirPods models
    """

    AIRPODS_MANUFACTURER = 76
    RECENT_BEACONS_MAX_T_NS = 10000000000

    MODEL_DATA_LENGTHS = {'a': 27, 'e': 54, '3': 54, 'f': 54, '2': 54}

    def __init__(self, min_rssi=-60):
        """
        Initialize AirPods monitor.

        Args:
            min_rssi: Minimum RSSI value to consider device in range
        """
        self.MIN_RSSI = min_rssi
        self.recent_beacons = []
        self.found_device = None
        self.found_data = None

    async def detection_callback(self, device, advertisement_data):
        """Process discovered BLE device."""
        logging.debug(f'Found device: {device.address}')
        logging.debug(f'Advertisement data: {advertisement_data}')
        logging.debug(f'RSSI: {advertisement_data.rssi}')

        if (
            advertisement_data.rssi >= self.MIN_RSSI
            and self.AIRPODS_MANUFACTURER
            in advertisement_data.manufacturer_data
        ):
            data = advertisement_data.manufacturer_data[
                self.AIRPODS_MANUFACTURER
            ]

            if len(data) >= 27:
                if (
                    data[0] == 0x07
                    or data[0] == 0x01
                    or data[0] == 0x0A
                    or data[0] == 0x12
                ):
                    best_device = self.get_best_result(
                        device, advertisement_data
                    )
                    if best_device is not None:
                        self.found_device = best_device['device']
                        self.found_data = data

                        logging.debug(f'Found AirPods device: {device.address}')
                        logging.debug(f'Data prefix: {hex(data[0])}')
                        logging.debug(
                            f'Manufacturer data length: {len(self.found_data)}'
                        )
                        logging.debug(f'Raw data: {data.hex()}')

    def get_best_result(self, device, advertisement_data):
        """Get the device with strongest signal from recent beacons."""
        current_beacon = {
            'time': time_ns(),
            'device': device,
            'rssi': advertisement_data.rssi,
        }

        self.recent_beacons.append(current_beacon)

        self.recent_beacons = [
            beacon
            for beacon in self.recent_beacons
            if time_ns() - beacon['time'] <= self.RECENT_BEACONS_MAX_T_NS
        ]

        strongest_beacon = max(
            self.recent_beacons, key=lambda x: x['rssi'], default=current_beacon
        )

        if strongest_beacon['device'].address == device.address:
            return current_beacon

        return strongest_beacon

    async def find_airpods(self):
        """Scan for AirPods devices."""
        try:
            self.found_device = None
            self.found_data = None

            for attempt in range(3):
                logging.debug(f'\nAttempt {attempt + 1}/3')

                scanner = BleakScanner(
                    detection_callback=self.detection_callback,
                    scanning_mode='active',
                )

                await scanner.start()
                await asyncio.sleep(5.0)
                await scanner.stop()

                if self.found_data and len(self.found_data) >= 27:
                    logging.debug(
                        f'Found valid AirPods data with length: {len(self.found_data)}'
                    )
                    logging.debug(f'Data: {self.found_data.hex()}')
                    return hexlify(bytearray(self.found_data))

                if attempt < 2:
                    await asyncio.sleep(1.0)

            logging.debug('No valid AirPods data found after all attempts')
            return None

        except Exception as e:
            logging.error(f'Error during scanning: {e}')
            logging.debug(traceback.format_exc())
            return None

    def decode_airpods_max_battery(self, raw):
        """Decode battery and charging status for AirPods Max.

        Decodes data according to the format::

            0x12     - Message type for AirPods Max
            byte[12] - Battery level (lower 4 bits)
            byte[14] - Charging flags (0x01 = right, 0x02 = left)

        Args:
            raw: Raw data in hex format

        Returns:
            dict: Battery levels and charging status
        """
        try:
            raw_bytes = bytes.fromhex(raw.decode())

            battery_byte = raw_bytes[12] & 0x0F
            battery_value = battery_byte

            charging_status = raw_bytes[14]
            charging_right = (charging_status & 0x01) != 0
            charging_left = (charging_status & 0x02) != 0

            logging.debug(f'Raw battery byte: {hex(raw_bytes[12])}')
            logging.debug(f'Battery value: {battery_value}')
            logging.debug(f'Raw charging status: {hex(charging_status)}')
            logging.debug(
                f'Charging left: {charging_left}, right: {charging_right}'
            )

            return {
                'left': battery_value,
                'right': battery_value,
                'case': None,
                'charging_left': charging_left,
                'charging_right': charging_right,
                'charging_case': None,
            }
        except Exception as e:
            logging.error(f'Error decoding AirPods Max battery: {e}')
            logging.debug(traceback.format_exc())
            return {
                'left': -1,
                'right': -1,
                'case': None,
                'charging_left': False,
                'charging_right': False,
                'charging_case': None,
            }

    def decode_regular_airpods(self, raw, flip):
        """Decode battery and charging status for regular AirPods."""
        try:
            raw_bytes = bytes.fromhex(raw.decode())

            left_status = raw_bytes[12 if flip else 13] & 0x0F
            right_status = raw_bytes[13 if flip else 12] & 0x0F
            case_status = raw_bytes[15] & 0x0F

            charging_byte = raw_bytes[14]
            charging_left = (
                charging_byte & (0b00000010 if flip else 0b00000001)
            ) != 0
            charging_right = (
                charging_byte & (0b00000001 if flip else 0b00000010)
            ) != 0
            charging_case = (charging_byte & 0b00000100) != 0

            logging.debug(f'Charging byte: {hex(charging_byte)}')
            logging.debug(f'Flip: {flip}')
            logging.debug(
                f'Charging status: L={charging_left}, R={charging_right}, C={charging_case}'
            )

            return {
                'left': left_status,
                'right': right_status,
                'case': case_status,
                'charging_left': charging_left,
                'charging_right': charging_right,
                'charging_case': charging_case,
            }
        except Exception as e:
            logging.error(f'Error decoding regular AirPods: {e}')
            logging.debug(traceback.format_exc())
            return {
                'left': -1,
                'right': -1,
                'case': -1,
                'charging_left': False,
                'charging_right': False,
                'charging_case': False,
            }

    def is_flipped(self, raw):
        """Check if left and right AirPods are flipped."""
        try:
            raw_bytes = bytes.fromhex(raw.decode())
            return (raw_bytes[10] & 0x02) == 0
        except Exception as e:
            logging.error(f'Error checking flip status: {e}')
            return False

    async def get_data(self):
        """Get complete status of AirPods device."""
        try:
            raw = await self.find_airpods()

            if raw is None:
                return dict(status=0, model='AirPods not found')

            raw_bytes = bytes.fromhex(raw.decode())
            logging.debug(f'Processing raw bytes: {raw_bytes.hex()}')

            message_type = raw_bytes[0]

            if message_type == 0x12 and len(raw_bytes) == 27:
                logging.debug('Detected AirPods Max format')
                model = 'AirPodsMax'
                status_data = self.decode_airpods_max_battery(raw)
            elif len(raw_bytes) == 54:
                model_identifier = raw_bytes[7]
                model_map = {
                    0x0E: 'AirPodsPro',
                    0x03: 'AirPods3',
                    0x0F: 'AirPods2',
                    0x02: 'AirPods1',
                }
                model = model_map.get(model_identifier, 'unknown')
                logging.debug(f'Model identifier byte: {hex(model_identifier)}')
                logging.debug(f'Mapped to model: {model}')

                if model == 'unknown':
                    return dict(
                        status=0,
                        error=f'Unknown model identifier: {hex(model_identifier)}',
                    )

                flip = self.is_flipped(raw)
                status_data = self.decode_regular_airpods(raw, flip)
            else:
                return dict(
                    status=0,
                    error=f'Invalid data format: message_type={hex(message_type)}, length={len(raw_bytes)}',
                )

            return dict(
                status=1,
                model=model,
                charge=dict(
                    left=status_data['left'],
                    right=status_data['right'],
                    case=status_data['case'],
                ),
                charging_left=status_data['charging_left'],
                charging_right=status_data['charging_right'],
                charging_case=status_data['charging_case'],
                date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                raw=raw.decode('utf-8')
                if logging.getLogger().level == logging.DEBUG
                else None,
            )

        except Exception as e:
            logging.error(f'Error in get_data: {e}')
            logging.debug(traceback.format_exc())
            return dict(status=0, error=str(e))


def format_output(data):
    """Format the output data with emoji decorations."""
    if data['status'] == 0:
        return f"❌ Error: {data.get('error', 'Unknown error')}"

    if data['model'] == 'AirPodsMax':
        return (
            f"🎧 {data['model']}\n"
            f"Battery: {data['charge']['left']}% "
            f"{'⚡' if data['charging_left'] else ''}"
        )

    output = [
        f"🎧 {data['model']}",
        f"Left:  {data['charge']['left']}% {'⚡' if data['charging_left'] else ''}",
        f"Right: {data['charge']['right']}% {'⚡' if data['charging_right'] else ''}",
    ]
    if data['charge']['case'] is not None:
        output.append(
            f"Case:  {data['charge']['case']}% "
            f"{'⚡' if data['charging_case'] else ''}"
        )
    return '\n'.join(output)


async def main():
    """Main function for CLI usage."""
    parser = argparse.ArgumentParser(description='AirPods Battery Monitor')
    parser.add_argument(
        '--json', action='store_true', help='Output in JSON format'
    )
    parser.add_argument(
        '--debug', action='store_true', help='Enable debug output'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=0,
        help='Update interval in seconds (0 for single check)',
    )
    parser.add_argument(
        '--min-rssi',
        type=float,
        default=-90,
        help='Minimum RSSI value (default: -90)',
    )
    parser.add_argument('--output', type=str, help='Output file for logging')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(message)s',
    )

    monitor = AirPodsMonitor(min_rssi=args.min_rssi)

    while True:
        try:
            data = await monitor.get_data()

            if args.json:
                output = dumps(data, indent=2)
            else:
                output = format_output(data)

            print(output)

            if args.output:
                with open(args.output, 'a') as f:
                    f.write(f'{output}\n')

            if args.interval == 0:
                break

            await asyncio.sleep(args.interval)

        except KeyboardInterrupt:
            logging.info('\nStopping...')
            break
        except Exception as e:
            logging.error(f'Error: {e}')
            logging.debug(traceback.format_exc())
            if args.interval == 0:
                break
            await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(main())
