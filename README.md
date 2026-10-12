# HP Scanjet 200: experimental SANE backend

A standalone SANE backend for the **HP Scanjet 200, USB 03f0:1c05**.
Designed for Ubuntu 18.04. XSane does not need modifications.

The C backend invokes a Python/libusb worker based on the USB protocol
implementation in [kropochev/scanjet200](https://github.com/kropochev/scanjet200).
See `UPSTREAM.txt` for the exact upstream revision and `LICENSE` for its MIT license.
This is an independent experimental project, not an official HP or SANE release.

## Features

- 300 dpi; RGB color and grayscale, 8 bits per channel
- A4 and rectangular selection; software cropping
- Per-column two-point dark/white calibration
- Cancellation requests parking through the Python worker

## Installation

Unpack or clone this repository and open a terminal in its root directory.

```bash
sudo apt update
sudo apt install build-essential libsane-dev libusb-1.0-0-dev sane-utils xsane python3-usb python3-numpy python3-pil
sudo bash install.sh
```

Reconnect the scanner and check detection as your normal desktop user:

```bash
scanimage -L
```

Expected device: `hp200:usb`. Installation adds a separate backend and does
not replace the Epson drivers or the main `dll.conf`.

## Calibration: required before scanning

No scanner-specific calibration is distributed. Close scanning applications,
place a clean blank white A4 sheet directly on the glass and close the lid:

```bash
sudo bash calibrate.sh
```

Press Enter when ready. Two short passes measure dark and white reference.
The validated profile is installed at
`/usr/local/share/hp200-sane/calibration-300.npz`.
Do not calibrate while XSane or another scanner process is running.
Repeat this command if a new profile is needed. Existing calibration is
replaced only after a successful measurement. Do not commit profiles to Git.

## First scan

Replace the white reference with your document, close the lid, then:

```bash
scanimage -d hp200:usb --mode Color --resolution 300 -l 0 -t 0 -x 210 -y 30 --format=pnm > test.pnm 2> test.log
xdg-open test.pnm
xsane hp200:usb
```

Use XSane as the normal user, without sudo. Disable frontend automatic color
adjustments for the first comparison with the calibrated Python output.
Image acquisition and decoding finish before pixels reach the frontend, so
XSane may appear busy without progress during acquisition. Preview has no
lower-resolution hardware mode. A Y crop captures down to the crop bottom.

## Status and limits

Direct Python capture and calibration have been confirmed on one scanner
under Ubuntu 18.04. Detection through the installed SANE backend has been
confirmed (`hp200:usb`). Full hardware scanning through XSane has not yet been
reported in this project. There is no support for ADF, other resolutions,
nonblocking I/O or network/saned operation.

C backend tests cover byte streaming, crops, grayscale parameters,
resolution constraints, repeat scans, invalid geometry and cancellation.
The worker has been compared against the original decoder on real RAW data
with a validated calibration. These tests do not replace hardware testing.

After Cancel, wait for the carriage to park; a new scan may temporarily report
busy. Closing the frontend may wait for USB timeouts and parking. Avoid forced
termination while the carriage is moving. Disconnect USB if it starts hitting
an end stop or produces abnormal mechanical noise.

## Diagnostics and removal

```bash
SANE_DEBUG_DLL=128 scanimage -L 2> detection.log
sudo bash uninstall.sh
```

Worker errors are written to stderr and appear in `test.log`.
For USB permissions reconnect in an active local desktop session.
Uninstall removes this package, including its installed calibration, and
keeps your original Python driver directory and other scanner backends.

## Development

```bash
make
make test
```

Tests use a simulated worker, not a scanner. Never install the test library.
The backend links to the system libusb and uses the system SANE headers.
Source is compiled on the target system, not shipped as a prebuilt binary.

Czech instructions: [README_CZ.txt](README_CZ.txt).
SANE API: https://sane-project.org/html/doc012.html

## License and attribution

MIT; retain the original copyright notice. USB initialization payloads and
Python communication logic derive from the upstream project. Calibration
profiles and user scans are not included. Contributions and hardware reports
are welcome; please distinguish verified behavior from proposed support.
