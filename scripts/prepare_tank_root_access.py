"""Authorize this PC's ADB key and ADB shell root before leaving TWRP.

Magisk policy schema/version/ALLOW value are from the official v23.0 sources
saved in analysis/magisk-v23-db.cpp and analysis/magisk-v23-db.hpp.
"""
from pathlib import Path
import shutil
import sqlite3
import subprocess

root = Path(__file__).resolve().parents[1]
run_dir = root / 'analysis/amonet-live-20261025-154149'
serial = 'G070L81694972B80'

def adb(*arguments, timeout=30):
    result = subprocess.run(['adb','-s',serial,*arguments], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).decode('utf-8', errors='replace'))
    return result.stdout.decode('utf-8', errors='replace').strip()

if 'uid=0(root)' not in adb('shell','id'):
    raise SystemExit('Rooted recovery required')
adb('shell','twrp','mount','/system')
version = adb('shell','/data/adb/magisk/magisk32','-c')
if '23.0' not in version:
    raise SystemExit('Magisk 23 must be installed first')

exists = adb('shell', 'if [ -f /data/adb/magisk.db ]; then echo EXISTS; else echo MISSING; fi')
local_db = run_dir / 'magisk-adb-policy.db'
if exists == 'EXISTS':
    original_db = run_dir / 'magisk-db-before-adb-policy.db'
    adb('pull','/data/adb/magisk.db',str(original_db))
    shutil.copyfile(original_db, local_db)
elif exists != 'MISSING':
    raise SystemExit(f'Unexpected database state: {exists}')
with sqlite3.connect(local_db) as database:
    user_version = database.execute('PRAGMA user_version').fetchone()[0]
    if user_version > 10:
        raise SystemExit('Unexpected newer Magisk database')
    database.executescript('''
        CREATE TABLE IF NOT EXISTS policies
          (uid INT, package_name TEXT, policy INT, until INT,
           logging INT, notification INT, PRIMARY KEY(uid));
        CREATE TABLE IF NOT EXISTS settings (key TEXT, value INT, PRIMARY KEY(key));
        CREATE TABLE IF NOT EXISTS strings (key TEXT, value TEXT, PRIMARY KEY(key));
        CREATE TABLE IF NOT EXISTS hidelist
          (package_name TEXT, process TEXT, PRIMARY KEY(package_name, process));
        INSERT OR REPLACE INTO policies
          (uid, package_name, policy, until, logging, notification)
          VALUES (2000, 'com.android.shell', 2, 0, 1, 1);
        INSERT OR REPLACE INTO settings (key, value) VALUES ('root_access', 3);
        PRAGMA user_version=10;
    ''')
    if database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise SystemExit('Magisk database integrity check failed')
adb('push',str(local_db),'/data/adb/magisk.db.new')
print(adb('shell', 'chown 0:0 /data/adb/magisk.db.new && chmod 600 /data/adb/magisk.db.new && mv /data/adb/magisk.db.new /data/adb/magisk.db && echo ADB_ROOT_POLICY_INSTALLED'), flush=True)

original_keys = run_dir / 'adb-keys-before-root.txt'
adb('pull','/data/misc/adb/adb_keys',str(original_keys))
lines = [line for line in original_keys.read_text(encoding='utf-8').splitlines() if line.strip()]
key_path = Path.home() / '.android/adbkey.pub'
pc_key = key_path.read_text(encoding='utf-8').strip()
added = not any(line.split()[0] == pc_key.split()[0] for line in lines)
if added:
    lines.append(pc_key)
    merged_keys = run_dir / 'adb-keys-with-this-pc.txt'
    merged_keys.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    adb('push',str(merged_keys),'/data/misc/adb/adb_keys.new')
    adb('shell', 'chown 1000:2000 /data/misc/adb/adb_keys.new && chmod 640 /data/misc/adb/adb_keys.new && mv /data/misc/adb/adb_keys.new /data/misc/adb/adb_keys')
print(f'PC_ADB_KEY_AUTHORIZED added={added}', flush=True)
print('USB_CONFIG=' + adb('shell','cat','/data/property/persist.sys.usb.config'), flush=True)
print('ROOT_ACCESS_PREPARED_NOT_YET_REBOOTED', flush=True)
