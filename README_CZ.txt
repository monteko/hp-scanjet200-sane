HP Scanjet 200 pro SANE / XSane – experimentální verze 0.1

Rozhraní SANE v C + samostatný Python pracovní proces.
Používá uživatelem ověřený scanjet200.py; vlastní profil se vytvoří po instalaci.
Původní komunikační protokol pochází z kropochev/scanjet200, licence MIT.
Tento balíček není oficiální ovladač HP ani součást projektu SANE.
Kalibrační profil není přiložen. Vytvořte jej pro svůj kus skeneru.

FUNKCE
- USB ID 03f0:1c05, SANE jméno hp200:usb
- barevný RGB nebo stupně šedi, 8 bitů na kanál
- 300 dpi, plocha A4, volitelný obdélník
- kalibrace sloupců a barevných kanálů z vlastního profilu
- předávání obrazu přes standardní SANE API, bez úprav XSane
- zrušení pošle Pythonu SIGINT, program se pokusí vrátit hlavu domů

INSTALACE V UBUNTU 18.04
1. Rozbalte ZIP. Otevřete terminál ve složce hp200-sane.
2. Nainstalujte závislosti:
   sudo apt update
   sudo apt install build-essential libsane-dev libusb-1.0-0-dev sane-utils xsane python3-usb python3-numpy python3-pil
3. Instalace:
   sudo bash install.sh
   Instalační skript znovu sestaví knihovnu na vašem Ubuntu. ZIP neobsahuje
   předem sestavenou knihovnu závislou na verzi glibc jiného systému.
4. Odpojte a připojte USB skeneru. Zavřete ostatní skenovací programy.
5. Jako běžný uživatel:
   scanimage -L
   Mělo by přibýt hp200:usb. Detekce neprovádí sken ani pohyb hlavy.
6. Před prvním skenem vložte čistý bílý papír A4, zavřete víko:
   sudo bash calibrate.sh
   Bez profilu sken skončí chybou. Skript bezpečně nahradí profil až po
   úspěšném změření a validaci. Kalibraci nespouštějte souběžně s XSane.
7. Krátký test – předloha na skle, víko zavřené:
   scanimage -d hp200:usb --mode Color --resolution 300 -l 0 -t 0 -x 210 -y 30 --format=pnm > hp200-test.pnm 2> hp200-test.log
   xdg-open hp200-test.pnm
   PNM (PPM) je zvoleno pro kompatibilitu starého scanimage.
8. XSane:
   xsane hp200:usb
   Nezapínejte automatické úpravy barev při prvním porovnání s Pythonem.
   V XSane lze potom uložit JPEG/PNG/PDF podle možností aplikace.

JAK PRACUJE
V sane_start se nejprve dokončí fyzický průchod a kalibrované dekódování.
Až potom se data předají frontendové aplikaci. Během tohoto čekání nemusí
XSane ukazovat postup a může působit zaneprázdněně. Nezavírejte ho násilně.
Výřez v X je softwarový; při Y se skenuje od horního okraje až ke konci
výřezu. Preview může být stejně rychlé jako běžný sken stejné výšky.
Není podpora jiného DPI, ADF ani neblokujícího SANE I/O. Více současných
otevření v jednom procesu je odmítnuto. Worker zamyká současné relace
stejného uživatele; libusb navíc vyžaduje výhradní otevření USB rozhraní.
Po Cancel počkejte na návrat hlavy. Nový scan může krátce hlásit obsazeno.
Při zavření aplikace backend čeká na ukončení workeru a návrat hlavy;
USB timeout a parkování mohou znamenat čekání přes minutu.
Nepoužívejte současně původní přímý Python program a XSane.

UMÍSTĚNÍ
/usr/local/share/hp200-sane/ – Python, inicializační data a kalibrace
/usr/lib/<architektura>/sane/libsane-hp200.so.1 – lokálně sestavená knihovna
/etc/sane.d/dll.d/hp200 – aktivace pouze tohoto backendu
/etc/udev/rules.d/70-hp200-sane.rules – přístup pro aktivní lokální relaci
Ostatní backendy ani hlavní dll.conf instalátor nepřepisuje.
Instalace při existujících cílech skončí, aby nepřepsala předchozí ovladač.

DIAGNOSTIKA
Pokud se HP neobjeví:
   SANE_DEBUG_DLL=128 scanimage -L 2> hp200-detection.log
Pokud scan selže, pošlete hp200-test.log (chyby workeru jsou na stderr).
Pokud jde o USB oprávnění, zkontrolujte nejprve opětovné připojení skeneru
v aktivní místní desktopové relaci. XSane nespouštějte pomocí sudo.
Samotnou detekci lze pro rozlišení oprávnění vyzkoušet sudo scanimage -L.
Pokud nefunguje kalibrace, profil lze nahradit nově ověřeným profilem:
   sudo install -m 644 /cesta/calibration-300.npz /usr/local/share/hp200-sane/calibration-300.npz
Profil neměňte během skenování.

ODINSTALACE
Ve složce balíčku:
   sudo bash uninstall.sh
Tento příkaz odstraní soubory tohoto balíčku, nikoli původní složku s
Python ovladačem, původní kalibraci nebo Epson. Nepoužívejte jej pro
jinou instalaci, která používá stejný název hp200.

OVĚŘENÍ ZDE
- knihovna sestavena s -Wall -Wextra -Werror proti skutečným SANE hlavičkám
- čtyři automatizované integrační testy C API se simulovaným workerem:
  barevná data a výřez, opakovaný scan, šedý režim, DPI, Cancel během start,
  neplatná geometrie, odmítnutí druhého otevření
- Python worker porovnán bajt po bajtu s původním dekodérem na přiložených
  skutečných RAW datech a kalibraci, barevně i v šedé
- kontrola instalačních shell skriptů
- skutečný skener, XSane ani Ubuntu 18.04 zde nejsou dostupné;
  hardware a načtení přes distro SANE je třeba ověřit u uživatele

Volitelné testy zdrojů po instalaci závislostí: make test
Testy nepohybují skenerem. Neinstalujte tests/backend-test.so do systému.
Specifikace SANE: https://sane-project.org/html/doc012.html
