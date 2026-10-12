#!/usr/bin/env python3
"""Experimental Linux port of kropochev/scanjet200 (MIT), Python >=3.6.
Only HP 03f0:1c05, hardware pass 300 dpi. Not a SANE backend.
"""
import argparse
import json
import logging
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import time

DATA = Path(__file__).resolve().parent / 'data'
LOG = logging.getLogger('scanjet200')
WIDTH, PAGE_ROWS, CHUNK, FEED = 2580, 3508, 196080, 543


def load_program(rows, lamp_off=False):
    blob = bytearray((DATA / 'hp_300.bin').read_bytes())
    ops, start, line_index, feed_index = [], None, None, None
    for line in (DATA / 'hp_300.txt').read_text().splitlines():
        fields = line.split()
        if not fields:
            continue
        kind, nums = fields[0], [int(x) for x in fields[1:]]
        sizes = {'CO': 5, 'CI': 4, 'BO': 2, 'BI': 1}
        if kind not in sizes or len(nums) != sizes[kind]:
            raise ValueError('Invalid captured operation: ' + line)
        if kind in ('CO', 'BO'):
            offset, length = nums[-2:]
            if min(offset, length) < 0 or offset + length > len(blob):
                raise ValueError('Captured payload out of bounds')
        if kind == 'CO' and nums[0:2] == [4, 0x83] and start is None:
            off, length = nums[-2:]
            for i in range(off, off + length - 1, 2):
                if blob[i] == 0x25:
                    line_index = len(ops)
                if blob[i] == 0x3d:
                    feed_index = len(ops)
                if length == 2 and blob[i:i+2] == b'\x0f\xff':
                    start = len(ops)
        ops.append((kind, nums))
    if start is None or line_index is None or feed_index is None:
        raise ValueError('Missing captured start/geometry writes')
    for idx, address, value in [(line_index, 0x25, rows * 3), (feed_index, 0x3d, FEED)]:
        off, length = ops[idx][1][-2:]
        found = set()
        for i in range(off, off + length - 1, 2):
            reg = blob[i]
            if address <= reg <= address + 2:
                blob[i+1] = (value >> (8 * (address + 2 - reg))) & 255
                found.add(reg)
        if len(found) != 3:
            raise ValueError('Incomplete geometry write')
    if lamp_off:
        for kind, nums in ops[:start]:
            if kind == 'CO' and nums[:2] == [4, 0x83]:
                off, length = nums[-2:]
                for i in range(off, off + length - 1, 2):
                    if blob[i] == 3:
                        blob[i+1] &= ~0x10
    return ops[:start+1], blob


class Scanner:
    def __init__(self):
        import usb.core
        import usb.util
        self.core, self.util = usb.core, usb.util
        self.dev = usb.core.find(idVendor=0x03f0, idProduct=0x1c05)
        if self.dev is None:
            raise RuntimeError('HP Scanjet 200 (03f0:1c05) nenalezen na USB')
        self.claimed = False
        self.detached = False

    def open(self):
        try:
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)
                self.detached = True
            if self.dev.get_active_configuration().bConfigurationValue != 1:
                self.dev.set_configuration(1)
            self.util.claim_interface(self.dev, 0)
            self.claimed = True
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.claimed:
            self.util.release_interface(self.dev, 0)
            self.claimed = False
        if self.detached:
            try:
                self.dev.attach_kernel_driver(0)
            except self.core.USBError:
                pass
            self.detached = False
        self.util.dispose_resources(self.dev)

    def ci(self, req, value, index, length):
        LOG.debug('CI %d %d %d %d', req, value, index, length)
        return bytes(self.dev.ctrl_transfer(0xc0, req, value, index, length, timeout=5000))

    def co(self, req, value, index, data):
        LOG.debug('CO %d %d %d length=%d', req, value, index, len(data))
        n = self.dev.ctrl_transfer(0x40, req, value, index, bytes(data), timeout=5000)
        if n != len(data):
            raise RuntimeError('Short control OUT')

    def reg(self, addr):
        data = self.ci(4, 0x8e | (0x100 if addr > 255 else 0),
                       (0x22 + (addr << 8)) & 0xffff, 2)
        if len(data) != 2 or data[1] != 0x55:
            raise RuntimeError('Invalid register reply: %04x %r' % (addr, data))
        return data[0]

    def wr(self, addr, value):
        self.co(4, 0x83 | (0x100 if addr > 255 else 0), 0, [addr & 255, value])

    def bo(self, data):
        if self.dev.write(0x02, bytes(data), timeout=5000) != len(data):
            raise RuntimeError('Short bulk OUT')

    def bi(self, size, timeout=1000):
        # PyUSB raises on timeout and cannot reliably expose partial bytes.
        # Read into supplied buffer and preserve transferred count where backend supports it.
        buffer = self.util.create_buffer(size)
        n = self.dev.read(0x81, buffer, timeout=timeout)
        return bytes(buffer[:n])

    def ahb(self, address, data):
        self.co(4, 0x82, 1, struct.pack('<II', address, len(data)))
        self.bo(data)

    def boot(self):
        boot = json.loads((DATA / 'boot.json').read_text())
        for addr, value in boot['registers']:
            self.wr(addr, value)
        for index, data in [(0x10, [0x0b]), (0x13, [0x0b]), (0x17, [0x8b, 0x09])]:
            self.co(0x0c, 0x8c, index, data)
        gamma = b''.join(struct.pack('<H', i) for i in range(256))
        for channel in range(3):
            self.ahb(0x01000000 + channel * 0x200, gamma)
        self.wr(0xbd, 0)
        self.wr(0xbe, 7)
        self.wr(0xa0, 8)
        self.wr(0x3c, 0x0a)
        for i, after in enumerate([0xa4, 0xaa, 0xac, 0xae, 0xb0]):
            if i == 3:
                self.wr(0xa0, 0)
                self.wr(0x3c, 0xaa)
            self.ahb(0x10000000 + i * 0x4000, boot['slope'])
            self.wr(after, 0)

    def replay(self, rows, lamp_off=False):
        ops, blob = load_program(rows, lamp_off)
        for kind, nums in ops:
            if kind == 'CO':
                req, val, idx, off, length = nums
                if req in (4, 12):
                    self.co(req, val, idx, blob[off:off+length])
            elif kind == 'CI':
                req, val, idx, length = nums
                if req in (4, 12):
                    try:
                        self.ci(req, val, idx, length)
                    except self.core.USBError as e:
                        LOG.debug('Ignored captured input: %s', e)
            elif kind == 'BO':
                off, length = nums
                self.bo(blob[off:off+length])
            elif kind == 'BI':
                try:
                    self.bi(nums[0], 2000)
                except self.core.USBError as e:
                    LOG.debug('Ignored captured drain: %s', e)

    def wait_data(self):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            value = self.reg(0x100)
            if value & 1 and not value & 0x80:
                return
            time.sleep(.005)
        raise RuntimeError('Timeout: scanner image data not ready')

    def home(self, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            s = self.reg(0x101)
            if s & 8 and not s & 1:
                return True
            time.sleep(.02)
        return False

    def park(self):
        for _ in range(2):
            self.wr(0x0a, 0x40)
            self.wr(0x01, 0xc0)
        if not self.home():
            raise RuntimeError('Carriage did not return home; disconnect USB before next test')

    def capture(self, rows, path, lamp_off=False):
        # Do not change boot registers while a previous pass is moving.
        status = self.reg(0x101)
        if status & 1 and not self.home():
            raise RuntimeError('Previous scan still moving')
        self.boot()
        status = self.reg(0x101)
        if status and not (status & 8 and not status & 1):
            raise RuntimeError('Carriage is not home; reconnect USB and retry')
        expected, received = rows * 3 * WIDTH * 2, 0
        started = False
        try:
            started = True  # cleanup also if replay fails after starting motor
            self.replay(rows, lamp_off)
            with open(str(path), 'wb') as sink:
                while received < expected:
                    self.wait_data()
                    want = min(CHUNK, expected - received)
                    self.co(4, 0x82, 0, struct.pack('<II', 0x10000000, want))
                    # Read a requested DRAM chunk completely before issuing another header.
                    remaining = want
                    while remaining:
                        data = self.bi(remaining, 30000)
                        if not data:
                            raise RuntimeError('Empty image transfer')
                        sink.write(data)
                        received += len(data)
                        remaining -= len(data)
                    LOG.info('Capture %d/%d bytes (%.0f%%)', received, expected, received * 100 / expected)
        finally:
            if started:
                try:
                    self.park()
                except Exception:
                    LOG.exception('Failed to park carriage')
                    raise
        if received != expected:
            raise RuntimeError('Incomplete frame')


def raw_image(raw, rows):
    import numpy as np
    planes = np.fromfile(str(raw), dtype='>u2')
    if planes.size != rows * 3 * WIDTH:
        raise ValueError('Incomplete raw frame')
    return planes.reshape(rows, 3, WIDTH)[:, :, ::-1].transpose(0, 2, 1)


def make_profile(dark_raw, white_raw, dark_rows, white_rows, path):
    import numpy as np
    dark = raw_image(dark_raw, dark_rows)[20:].mean(axis=0)
    white = raw_image(white_raw, white_rows)[white_rows//5:white_rows*4//5:3].mean(axis=0)
    if np.median(dark[:, 1]) >= 16384:
        raise ValueError('Dark reference too bright: lamp did not switch off')
    if np.median(white[:2486, 1]) <= max(4096, 2*np.median(dark[:2486, 1])):
        raise ValueError('White reference too dark')
    if np.mean((white-dark)[:2486] < 2048) > .01:
        raise ValueError('White paper does not cover sensor or insufficient signal')
    saturated = np.mean(white[:2486] >= 65000, axis=0)
    LOG.warning('White reference near clipping R/G/B: %s; clipped detail cannot be restored', saturated)
    with open(str(path), 'wb') as sink:
        np.savez_compressed(sink, white=white.astype(np.float32),
                            dark=dark.astype(np.float32), dpi=np.array(300))


def decode(raw, rows, calibration=None):
    import numpy as np
    rgb = raw_image(raw, rows).astype(np.float32)
    if calibration is not None:
        with np.load(str(calibration), allow_pickle=False) as profile:
            white, dark = profile['white'], profile['dark']
            if white.shape != (WIDTH, 3) or dark.shape != (WIDTH, 3) or int(profile['dpi']) != 300:
                raise ValueError('Invalid calibration profile')
            if not np.isfinite(white).all() or not np.isfinite(dark).all():
                raise ValueError('Non-finite calibration profile')
            if np.any((white-dark)[:2486] <= 0):
                raise ValueError('Invalid white/dark separation')
        linear = np.clip((rgb[:, :2486] - dark[:2486]) / np.maximum(1, white[:2486]-dark[:2486]), 0, 1)
    else:
        rgb = rgb[:, :2486, :]
        low, high = np.percentile(rgb[::max(1, rows//100)], [2, 98])
        linear = np.clip((rgb - low) / max(1, high-low), 0, 1)
    encoded = np.where(linear <= .0031308, linear * 12.92,
                       1.055 * np.power(linear, 1/2.4) - .055)
    return np.rint(encoded * 255).clip(0, 255).astype(np.uint8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['list', 'probe', 'scan', 'calibrate', 'decode', 'check-data'])
    parser.add_argument('--height', type=float, default=30, help='height in mm, default 30; full A4: 297')
    parser.add_argument('-o', '--output', default='test.png')
    parser.add_argument('--raw', help='existing raw file for offline decode')
    parser.add_argument('--calibration', default='calibration-300.npz')
    parser.add_argument('--no-calibration', action='store_true')
    parser.add_argument('--keep-raw', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(levelname)s: %(message)s')
    if not math.isfinite(args.height) or not 1 <= args.height <= 297:
        parser.error('--height must be 1..297 mm')
    rows = min(PAGE_ROWS, round(PAGE_ROWS * args.height / 297))
    if args.command == 'check-data':
        ops, blob = load_program(rows)
        print('Captured data OK: %d operations, %d payload bytes, %d RGB rows' % (len(ops), len(blob), rows))
        return
    if args.command == 'decode':
        if not args.raw:
            parser.error('decode requires --raw')
        from PIL import Image
        output = Path(args.output).expanduser()
        if output.exists() or output.suffix.lower() not in ('.png', '.tif', '.tiff'):
            parser.error('Choose a new PNG/TIFF output path')
        size = Path(args.raw).stat().st_size
        if not size or size % (WIDTH*6) or size > PAGE_ROWS*WIDTH*6:
            parser.error('Invalid raw file size')
        profile = None if args.no_calibration else Path(args.calibration)
        if profile is not None and not profile.exists():
            parser.error('Calibration missing; use --no-calibration for original decoder')
        Image.fromarray(decode(args.raw, size//(WIDTH*6), profile), 'RGB').save(str(output), dpi=(300, 300))
        print('Saved: ' + str(output))
        return
    dev = Scanner()
    try:
        if args.command == 'list':
            print('HP Scanjet 200 03f0:1c05, bus=%s address=%s' % (dev.dev.bus, dev.dev.address))
            return
        dev.open()
        if args.command == 'probe':
            for address in [0x00, 0x06, 0x100, 0x101]:
                print('Register 0x%03x = 0x%02x' % (address, dev.reg(address)))
            return
        # Resolve dependencies and output before moving scanner.
        import numpy
        from PIL import Image
        if args.command == 'calibrate':
            profile = Path(args.calibration).expanduser().resolve()
            if profile.exists():
                raise RuntimeError('Calibration exists; choose a different --calibration path')
            print('Calibration: clean WHITE A4 must cover glass, lid closed.', flush=True)
            with tempfile.TemporaryDirectory(prefix='scanjet-cal-', dir=str(profile.parent)) as tmp:
                dark_raw, white_raw = Path(tmp)/'dark.raw', Path(tmp)/'white.raw'
                dark_rows, white_rows = round(PAGE_ROWS*20/297), round(PAGE_ROWS*60/297)
                dev.capture(dark_rows, dark_raw, lamp_off=True)
                dev.capture(white_rows, white_raw)
                make_profile(dark_raw, white_raw, dark_rows, white_rows, profile)
            print('Calibration saved: ' + str(profile))
            return
        output = Path(args.output).expanduser().resolve()
        if output.suffix.lower() not in ('.png', '.tif', '.tiff'):
            parser.error('Output must be .png or .tif/.tiff')
        if output.exists():
            raise RuntimeError('Output already exists: ' + str(output))
        fd, name = tempfile.mkstemp(prefix='scanjet200-', suffix='.raw', dir=str(output.parent))
        os.close(fd)
        raw = Path(name)
        try:
            dev.capture(rows, raw)
            Image.fromarray(decode(raw, rows, None if args.no_calibration or not Path(args.calibration).exists() else Path(args.calibration)), 'RGB').save(str(output), dpi=(300, 300))
            print('Saved: ' + str(output))
        finally:
            if args.keep_raw:
                print('Raw data: ' + str(raw))
            else:
                raw.unlink()
    finally:
        dev.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Cancelled', file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        LOG.exception('%s', error)
        sys.exit(1)
