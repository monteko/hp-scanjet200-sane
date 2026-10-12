#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ $EUID -ne 0 ]]; then echo 'Spusť: sudo bash install.sh'; exit 1; fi
multiarch=$(gcc -print-multiarch)
[[ -n $multiarch && $multiarch != */* ]] || { echo 'Nelze určit architekturu'; exit 1; }
libdir="/usr/lib/$multiarch/sane"
[[ -d $libdir && -d /etc/sane.d ]] || { echo 'Nejprve nainstaluj libsane-dev a sane-utils.'; exit 1; }
if [[ -e /usr/local/share/hp200-sane || -e /etc/sane.d/dll.d/hp200 || -e "$libdir/libsane-hp200.so.1" || -L "$libdir/libsane-hp200.so.1" || -e "$libdir/libsane-hp200.so" || -L "$libdir/libsane-hp200.so" || -e /etc/udev/rules.d/70-hp200-sane.rules ]]; then
 echo 'Tento ovladač už je nainstalovaný nebo cesty existují. Nejprve použij původní uninstall.sh.'; exit 1
fi
/usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0, 'driver')
import usb.core, numpy, PIL
from scanjet200 import load_program
load_program(3508)
print('Python a inicializační data OK; kalibrace se vytvoří po instalaci')
PY
# Always rebuild on the target Ubuntu. Do not install a binary built elsewhere.
make clean
make
install -d -m 755 /usr/local/share/hp200-sane
install -m 644 driver/scanjet200.py driver/sane_bridge.py /usr/local/share/hp200-sane/
install -d -m 755 /usr/local/share/hp200-sane/data
install -m 644 driver/data/* /usr/local/share/hp200-sane/data/
install -m 644 LICENSE UPSTREAM.txt /usr/local/share/hp200-sane/
install -m 755 libsane-hp200.so.1 "$libdir/libsane-hp200.so.1"
ln -s libsane-hp200.so.1 "$libdir/libsane-hp200.so"
install -d -m 755 /etc/sane.d/dll.d
printf 'hp200\n' > /etc/sane.d/dll.d/hp200
install -m 644 70-hp200-sane.rules /etc/udev/rules.d/70-hp200-sane.rules
udevadm control --reload-rules
printf 'Nainstalováno. Odpoj a připoj USB skeneru, pak spusť scanimage -L jako běžný uživatel.\n'
printf 'Před prvním skenem vytvoř vlastní kalibraci: sudo bash calibrate.sh\n'
