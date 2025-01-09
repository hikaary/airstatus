import argparse
import asyncio
import json
from binascii import hexlify
from datetime import datetime

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData


class AirPodsMonitor:
    AIRPODS_MANUFACTURER = 76
    MIN_RSSI = -70

    MODEL_IDENTIFIERS = {
        'a': {'name': 'AirPods Max', 'length': 27},
        'e': {'name': 'AirPods Pro', 'length': 54},
        '3': {'name': 'AirPods 3', 'length': 54},
        'f': {'name': 'AirPods 2', 'length': 54},
        '2': {'name': 'AirPods 1', 'length': 54},
    }

    def __init__(self, debug=False):
        self.debug = debug
        self.found_device = None
        self.found_data = None

    async def detection_callback(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ):
        if self.debug:
            print(f'\nFound device: {device.address}')
            print(f'Name: {device.name}')
            print(f'RSSI: {advertisement_data.rssi}')
            print(f'Manufacturer data: {advertisement_data.manufacturer_data}')

        if self.AIRPODS_MANUFACTURER in advertisement_data.manufacturer_data:
            data = advertisement_data.manufacturer_data[
                self.AIRPODS_MANUFACTURER
            ]
            hex_data = hexlify(data)

            if self.debug:
                print(f'Apple data length: {len(data)}')
                print(f'Raw data: {hex_data}')

            if len(data) == 27 and data[0] == 0x12:
                self.found_device = device
                self.found_data = data

    async def find_airpods(self):
        try:
            scanner = BleakScanner(
                detection_callback=self.detection_callback,
                scanning_mode='active',
            )

            await scanner.start()
            await asyncio.sleep(12.0)
            await scanner.stop()

            if self.found_data:
                return hexlify(self.found_data)
            return None

        except Exception as e:
            if self.debug:
                print(f'Error during scanning: {e}')
                import traceback

                traceback.print_exc()
            return None

    def decode_airpods_max_battery(self, data):
        try:
            if self.debug:
                print('Raw battery data:', ' '.join(f'{b:02x}' for b in data))

            battery_byte = data[12]
            battery_value = battery_byte & 0x0F

            charging = (data[14] & 0x80) != 0

            if self.debug:
                print(f'Battery byte: {battery_byte:02x}')
                print(f'Battery value: {battery_value}')
                print(f'Charging: {charging}')

            return {
                'left': battery_value,
                'right': battery_value,
                'case': None,
                'charging': {'left': charging, 'right': charging, 'case': None},
            }
        except Exception as e:
            if self.debug:
                print(f'Error decoding battery: {e}')
                import traceback

                traceback.print_exc()
            return {
                'left': -1,
                'right': -1,
                'case': None,
                'charging': {'left': False, 'right': False, 'case': None},
            }

    def decode_status(self, hex_data):
        try:
            data = bytes.fromhex(hex_data.decode('utf-8'))

            if len(data) == 27 and data[0] == 0x12:
                battery_info = self.decode_airpods_max_battery(data)
                return {
                    'status': 1,
                    'model': 'AirPods Max',
                    'battery': {
                        'left': battery_info['left'],
                        'right': battery_info['right'],
                        'case': None,
                    },
                    'charging': battery_info['charging'],
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'raw_data': hex_data.decode('utf-8')
                    if self.debug
                    else None,
                }

            return {'status': 0, 'error': 'Unsupported device type'}

        except Exception as e:
            if self.debug:
                print(f'Error decoding data: {e}')
                import traceback

                traceback.print_exc()
            return {'status': 0, 'error': str(e)}

    async def get_status(self, max_attempts=3):
        for attempt in range(max_attempts):
            hex_data = await self.find_airpods()
            if hex_data is not None:
                return self.decode_status(hex_data)
            if attempt < max_attempts - 1:
                await asyncio.sleep(1)
        return {'status': 0, 'error': 'AirPods Max not found'}


def format_output(data):
    if data['status'] == 0:
        return f"❌ Error: {data.get('error', 'Unknown error')}"

    if data['model'] == 'AirPods Max':
        battery = data['battery']['left']
        charging = data['charging']['left']
        return f"🎧 {data['model']}\nBattery: {battery}% {('⚡' if charging else '')}"
    else:
        output = [
            f"🎧 {data['model']}",
            f"Left:  {data['battery']['left']}% {'⚡' if data['charging']['left'] else ''}",
            f"Right: {data['battery']['right']}% {'⚡' if data['charging']['right'] else ''}",
        ]
        if data['battery']['case'] is not None:
            output.append(
                f"Case:  {data['battery']['case']}% {'⚡' if data['charging']['case'] else ''}"
            )
        return '\n'.join(output)


async def main():
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
    args = parser.parse_args()

    monitor = AirPodsMonitor(debug=args.debug)
    monitor.MIN_RSSI = args.min_rssi

    while True:
        try:
            status = await monitor.get_status()

            if args.json:
                print(json.dumps(status, indent=2))
            else:
                print(format_output(status))

            if args.interval == 0:
                break

            await asyncio.sleep(args.interval)
        except KeyboardInterrupt:
            print('\nStopping...')
            break
        except Exception as e:
            print(f'Error: {e}')
            if args.debug:
                import traceback

                print(traceback.format_exc())
            if args.interval == 0:
                break
            await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(main())
