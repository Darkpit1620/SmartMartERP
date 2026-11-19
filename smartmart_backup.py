"""Private verified SQLite + media backup for the SmartMartERP development installation.

Usage:
    python smartmart_backup.py
    python smartmart_backup.py --verify "C:\\Users\\USER\\Documents\\SmartMartERP_Backups\\..."

Backups are outside the Django/Git project. Never commit backup files to GitHub.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / 'db.sqlite3'
DEFAULT_TARGET = Path(os.environ.get('SMARTMART_BACKUP_DIR') or (Path.home() / 'Documents' / 'SmartMartERP_Backups'))
MEDIA_DIR = ROOT / 'media'


def hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check_database(path):
    # Verifies SQLite's structural integrity. No changes to the database.
    con = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        rows = [row[0] for row in con.execute('PRAGMA integrity_check;').fetchall()]
        if rows != ['ok']:
            raise RuntimeError('SQLite integrity check failed: ' + '; '.join(rows[:3]))
    finally:
        con.close()


def create_backup():
    if not DATABASE.is_file():
        raise RuntimeError('db.sqlite3 not found. Run this script from your existing SQLite SmartMartERP installation.')
    check_database(DATABASE)
    # Reject placing backups inside project even when environment variable is customized.
    target_base = DEFAULT_TARGET.expanduser().resolve()
    if target_base == ROOT.resolve() or ROOT.resolve() in target_base.parents:
        raise RuntimeError('Backup destination must be OUTSIDE the SmartMartERP project and Git repository.')
    target_base.mkdir(parents=True, exist_ok=True)
    output = target_base / ('SmartMart_Backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    output.mkdir(exist_ok=False)
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(),
                'note': 'Contains private supermarket operational data. Never upload publicly.',
                'files': {}}
    try:
        dest = output / 'db.sqlite3'
        src_con = sqlite3.connect(DATABASE.resolve().as_uri() + '?mode=ro', uri=True)
        dst_con = sqlite3.connect(str(dest))
        try:
            src_con.backup(dst_con)
        finally:
            dst_con.close()
            src_con.close()
        check_database(dest)
        manifest['files']['db.sqlite3'] = hash_file(dest)
        if MEDIA_DIR.is_dir():
            for item in MEDIA_DIR.rglob('*'):
                if item.is_symlink():
                    raise RuntimeError('Media has a symbolic link; review it before backup: ' + item.name)
                if item.is_file():
                    rel = item.relative_to(ROOT)
                    dst = output / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dst)
                    manifest['files'][rel.as_posix()] = hash_file(dst)
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        verify_backup(output)
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise
    return output


def verify_backup(folder):
    folder = Path(folder).expanduser().resolve()
    manifest_file = folder / 'manifest.json'
    if not manifest_file.is_file():
        raise RuntimeError('No manifest.json found in that backup folder.')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    files = manifest.get('files', {})
    if 'db.sqlite3' not in files:
        raise RuntimeError('Backup manifest is missing db.sqlite3.')
    for name, expected in files.items():
        candidate = (folder / name).resolve()
        if folder not in candidate.parents:
            raise RuntimeError('Unexpected backup filename in manifest.')
        if not candidate.is_file() or hash_file(candidate) != expected:
            raise RuntimeError('Missing or modified backup file: ' + name)
    check_database(folder / 'db.sqlite3')
    return len(files)


def main():
    parser = argparse.ArgumentParser(description='Back up and verify SmartMartERP SQLite data and uploaded media.')
    parser.add_argument('--verify', metavar='FOLDER', help='Verify a previous backup folder without modifying the live database.')
    args = parser.parse_args()
    try:
        if args.verify:
            count = verify_backup(args.verify)
            print('BACKUP VERIFIED:', count, 'files. SQLite integrity: OK.')
        else:
            folder = create_backup()
            print('PRIVATE BACKUP CREATED AND VERIFIED:', folder)
            print('Keep this folder outside GitHub. Test a full restore on a separate copy before going live.')
    except (OSError, RuntimeError, sqlite3.Error, ValueError, json.JSONDecodeError) as error:
        print('BACKUP FAILED SAFELY:', error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
