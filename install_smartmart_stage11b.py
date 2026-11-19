"""Non-destructive setup of Render staging scripts for SmartMart ERP.

Does not connect to GitHub/Render or modify existing models, data or local settings.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'stage11b_render'
FILES = {
    SRC / 'settings_render_staging.py': ROOT / 'config/settings_render_staging.py',
    SRC / 'render_staging_build.sh': ROOT / 'render_staging_build.sh',
    SRC / 'render_staging_start.sh': ROOT / 'render_staging_start.sh',
    SRC / 'smartmart_stage11b_preflight.py': ROOT / 'smartmart_stage11b_preflight.py',
}
MARKER = '# SMARTMART_STAGE11B_STAGING'
IGNORES = '\n' + MARKER + '\n/.env\n/.env.*\n/db.sqlite3\n/db.sqlite3-*\n/.venv/\n/media/\n/staticfiles/\n/SmartMart_*Backups/\n*.pem\n*.key\n'


def stop(message):
    raise SystemExit('STAGE 11B STOPPED SAFELY: ' + message)


def main():
    print('SMARTMART ERP STAGE 11B — RENDER STAGING PREPARATION', flush=True)
    required = [ROOT/'manage.py', ROOT/'db.sqlite3', ROOT/'config/settings.py',
                ROOT/'config/settings_production.py',
                ROOT/'deployment_stage10d/requirements-production.txt',
                ROOT/'smartmart_backup.py']
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        stop('Missing prerequisites: ' + ', '.join(missing) + '. Install Stage 10D first.')
    if not all(f.exists() for f in FILES):
        stop('Incomplete ZIP extraction. Extract the Stage 11B archive into SmartMartERP.')
    for source, target in FILES.items():
        if target.exists() and target.read_bytes() != source.read_bytes():
            stop('Existing customized file would be overwritten: ' + str(target.relative_to(ROOT)))
    ignore_file = ROOT / '.gitignore'
    old_ignore = ignore_file.read_text(encoding='utf-8') if ignore_file.exists() else None
    new_ignore = old_ignore or ''
    if MARKER not in new_ignore:
        new_ignore = new_ignore.rstrip('\n') + IGNORES
    version_file = ROOT/'.python-version'
    # Preserve an existing version selection, otherwise match user's local Python 3.12.
    create_version = not version_file.exists()
    changed = any(not f.exists() for f in FILES.values()) or new_ignore != (old_ignore or '') or create_version
    if not changed:
        print('Already installed; no files changed.')
        return 0
    try:
        from smartmart_backup import create_backup
        backup = create_backup()
    except Exception as exc:
        stop('Verified private backup failed; no files changed: ' + str(exc))
    print('Verified backup:', backup)
    created = []
    try:
        for source, target in FILES.items():
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                created.append(target)
        if create_version:
            version_file.write_text('3.12.10\n', encoding='utf-8')
            created.append(version_file)
        if new_ignore != (old_ignore or ''):
            ignore_file.write_text(new_ignore, encoding='utf-8')
        for f in (ROOT/'config/settings_render_staging.py', ROOT/'smartmart_stage11b_preflight.py'):
            compile(f.read_text(encoding='utf-8'), str(f), 'exec')
        check = subprocess.run([sys.executable, 'manage.py', 'check'], cwd=ROOT, check=False)
        if check.returncode:
            raise RuntimeError('Local Django system check did not pass')
    except Exception as exc:
        for f in created:
            if f.is_file():
                f.unlink()
        if old_ignore is None:
            if ignore_file.exists():
                ignore_file.unlink()
        else:
            ignore_file.write_text(old_ignore, encoding='utf-8')
        stop(str(exc) + '; original files restored.')
    print('Stage 11B files installed. Local settings and data were not modified.')
    print('NEXT: python smartmart_stage11b_preflight.py')
    print('THEN: Read stage11b_render/README_RENDER_STAGING.md before using Render.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
