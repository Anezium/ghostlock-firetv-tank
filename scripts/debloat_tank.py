"""Apply a small reversible Fire OS debloat, preserving third-party apps."""
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
run_dir = root / 'analysis/amonet-live-20261025-154149'
serial = 'G070L81694972B80'
targets = {
    'com.amazon.device.software.ota': 'OTA updater',
    'com.amazon.device.software.ota.override': 'OTA override',
    'com.amazon.tv.forcedotaupdater.v2': 'Forced OTA updater',
    'com.amazon.tv.easyupgrade': 'Upgrade component',
    'com.amazon.bueller.photos': 'Amazon Photos',
    'com.amazon.ftv.screensaver': 'Amazon screensaver',
    'com.amazon.alexashopping': 'Alexa shopping',
    'com.amazon.shoptv.client': 'Shop TV',
    'com.amazon.shoptv.firetv.client': 'Shop TV Fire TV',
    'com.amazon.kor.demo': 'Retail demo',
}
core = {'com.amazon.tv.launcher', 'com.amazon.avod', 'com.amazon.venezia',
        'com.amazon.tv.settings.core', 'com.amazon.tv.settings.v2',
        'com.amazon.tv.ime', 'com.amazon.fireinputdevices', 'com.amazon.vizzini'}

def adb(command, timeout=30):
    result = subprocess.run(['adb','-s',serial,'shell',command], capture_output=True, timeout=timeout)
    output = (result.stdout + result.stderr).decode('utf-8', errors='replace').strip()
    if result.returncode:
        raise RuntimeError(output)
    return output

def root_command(command):
    return adb(f"su -c '{command}'")

def package_set(flags=''):
    output = adb('pm list packages ' + flags)
    return {line.removeprefix('package:').strip() for line in output.splitlines()
            if line.startswith('package:')}

if 'uid=0(root)' not in root_command('id') or adb('getprop sys.boot_completed') != '1':
    raise SystemExit('Booted and rooted Fire OS required')
system_packages = package_set('-s')
installed = package_set()
disabled_before = package_set('-d')
third_party_before = package_set('-3')
enabled_core_before = core & package_set('-e')
snapshot = {'disabled_before': sorted(disabled_before),
            'third_party_before': sorted(third_party_before), 'targets': targets}
(run_dir / 'debloat-before.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
changed = []
skipped = []
for package, label in targets.items():
    if package not in installed or package not in system_packages or package in third_party_before:
        skipped.append(package)
        continue
    if package in disabled_before:
        continue
    details = root_command('dumpsys package ' + package)
    (run_dir / ('package-before-' + package + '.txt')).write_text(details, encoding='utf-8')
    result = root_command('pm disable-user --user 0 ' + package)
    print(f'{label}: {result}', flush=True)
    if 'disabled-user' not in result:
        raise RuntimeError(f'Disable not acknowledged for {package}')
    changed.append(package)
    root_command('am force-stop --user 0 ' + package)
    # Save an incremental record before processing the next package.
    (run_dir / 'debloat-changed.json').write_text(json.dumps(changed, indent=2), encoding='utf-8')
disabled_after = package_set('-d')
if not set(changed) <= disabled_after:
    raise SystemExit('Some changes did not persist')
if not third_party_before <= package_set('-3'):
    raise SystemExit('Third-party package inventory changed unexpectedly')
if not enabled_core_before <= package_set('-e'):
    raise SystemExit('A protected core package became disabled')
report = {'changed': changed, 'skipped': skipped, 'disabled_after': sorted(disabled_after),
          'third_party_preserved': True, 'core_packages_preserved': True,
          'data_cleared': False, 'packages_uninstalled': False}
(run_dir / 'debloat-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
undo = ["$adb = 'C:/Users/saim2/AppData/Local/Android/Sdk/platform-tools/adb.exe'", "$packages = @("]
ota = {'com.amazon.device.software.ota', 'com.amazon.device.software.ota.override',
       'com.amazon.tv.forcedotaupdater.v2', 'com.amazon.tv.easyupgrade'}
undo_apps = [package for package in changed if package not in ota]
undo.append('    # Les mises a jour OTA restent bloquees pour proteger le root.')
undo.extend("    '" + package + "'" + (',' if index < len(undo_apps) - 1 else '')
            for index, package in enumerate(undo_apps))
undo.extend([')', 'foreach ($package in $packages) {',
             '    & $adb -s G070L81694972B80 shell "su -c \'pm enable --user 0 $package\'"', '}'])
(root / 'scripts/UNDO-DEBLOAT.ps1').write_text('\n'.join(undo) + '\n', encoding='utf-8-sig')
print(json.dumps(report), flush=True)
