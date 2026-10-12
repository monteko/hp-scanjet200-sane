#!/bin/bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo 'Run: sudo bash calibrate.sh'; exit 1; fi
script=/usr/local/share/hp200-sane/scanjet200.py
[[ -f $script ]] || { echo 'Install backend first.'; exit 1; }
echo 'Place a clean blank WHITE A4 sheet on the glass, close the lid.'
echo 'Close XSane and other scanning applications. Two short passes will run.'
read -r -p 'Press Enter when ready (Ctrl+C cancels): ' answer
tmpdir=$(mktemp -d)
cleanup() { /usr/bin/python3 - "$tmpdir" <<'PYCODE'
import shutil, sys
shutil.rmtree(sys.argv[1])
PYCODE
}
trap cleanup EXIT
/usr/bin/python3 "$script" calibrate --calibration "$tmpdir/calibration-300.npz"
install -m 644 "$tmpdir/calibration-300.npz" /usr/local/share/hp200-sane/calibration-300.npz
echo 'Calibration installed. You can now scan using XSane.'
