#!/usr/bin/python3
"""SANE worker. stdout is exclusively SJ20 header and RGB/gray pixels."""
import contextlib
import fcntl
import logging
import os
from pathlib import Path
import signal
import struct
import sys
import tempfile
import traceback
import numpy as np
from scanjet200 import Scanner, decode, WIDTH, PAGE_ROWS


def interrupted(signum, frame):
    # First cancellation unwinds capture, whose finally parks the carriage.
    # Further SIGINT must not interrupt parking/USB resource release.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    raise KeyboardInterrupt


def main():
    x, y, width, height = [int(v) for v in sys.argv[1:5]]
    gray = sys.argv[5] == 'Gray'
    if not (0 <= x < 2486 and 0 <= y < PAGE_ROWS and
            1 <= width <= 2486-x and 1 <= height <= PAGE_ROWS-y):
        raise ValueError('Invalid scan rectangle')
    profile = Path(__file__).parent / 'calibration-300.npz'
    # Validate before moving the head.
    with np.load(str(profile), allow_pickle=False) as p:
        w, d = p['white'], p['dark']
        if w.shape != (WIDTH,3) or d.shape != w.shape or int(p['dpi']) != 300:
            raise ValueError('Invalid calibration')
        if not np.isfinite(w).all() or not np.isfinite(d).all() or np.any(w[:2486] <= d[:2486]):
            raise ValueError('Invalid calibration values')
    signal.signal(signal.SIGINT, interrupted)
    # Local lock prevents another XSane session starting while cancellation parks.
    fd = os.open('/tmp/hp200-sane-%d.lock' % os.getuid(),
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        scanner = Scanner()
        try:
            scanner.open()
            with tempfile.TemporaryDirectory(prefix='hp200-sane-') as tmp:
                raw = Path(tmp)/'frame.raw'
                scanner.capture(y+height, raw)
                image = decode(raw, y+height, profile)[y:y+height, x:x+width]
                if gray:
                    rgb = image.astype(np.uint32)
                    image = ((77*rgb[:,:,0]+150*rgb[:,:,1]+29*rgb[:,:,2]) >> 8).astype(np.uint8)
                output = sys.stdout.buffer
                output.write(struct.pack('<4sIII', b'SJ20', width, height, 1 if gray else 3))
                output.flush()
                for row in image:
                    output.write(row.tobytes())
                output.flush()
        finally:
            scanner.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='hp200: %(levelname)s: %(message)s')
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
