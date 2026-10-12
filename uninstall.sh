#!/bin/bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo 'Spusť: sudo bash uninstall.sh'; exit 1; fi
multiarch=$(gcc -print-multiarch)
[[ -n $multiarch && $multiarch != */* ]] || exit 1
libdir="/usr/lib/$multiarch/sane"
rm -f -- /etc/sane.d/dll.d/hp200 /etc/udev/rules.d/70-hp200-sane.rules "$libdir/libsane-hp200.so" "$libdir/libsane-hp200.so.1"
# Only remove named files belonging to this package; preserve unexpected files.
rm -f -- /usr/local/share/hp200-sane/{scanjet200.py,sane_bridge.py,calibration-300.npz,LICENSE,UPSTREAM.txt}
rm -f -- /usr/local/share/hp200-sane/__pycache__/scanjet200.cpython-*.pyc
rmdir /usr/local/share/hp200-sane/__pycache__ 2>/dev/null || true
rm -f -- /usr/local/share/hp200-sane/data/{hp_300.bin,hp_300.txt,boot.json}
rmdir /usr/local/share/hp200-sane/data /usr/local/share/hp200-sane 2>/dev/null || true
udevadm control --reload-rules
printf 'Ovladač hp200 odstraněn. Původní Python program i Epson zůstávají dostupné.\n'
