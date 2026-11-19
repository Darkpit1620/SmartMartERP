"""Read-only checks before committing SmartMart ERP to a private Git repository."""
from pathlib import Path
import re
import subprocess
import sys

BASE = Path(__file__).resolve().parent
REQUIRED = [
    'manage.py', 'config/settings_production.py', 'config/settings_render_staging.py',
    'render_staging_build.sh', 'render_staging_start.sh',
    'deployment_stage10d/requirements-production.txt',
]
REJECT = [
    re.compile(r'(^|/)(db\.sqlite3(?:-.*)?|.*\.sqlite3?|.*\.db|.*\.pem|.*\.key)$', re.I),
    re.compile(r'(^|/)(\.env(?:\..*)?|\.venv|media|staticfiles|backups?|.*_backups)(/|$)', re.I),
]


def run(*args):
    return subprocess.run(args, cwd=BASE, capture_output=True, text=True)


def main():
    print('SMARTMART STAGE 11B: STAGING & GITHUB PREFLIGHT (READ ONLY)')
    missing = [f for f in REQUIRED if not (BASE / f).is_file()]
    if missing:
        print('STOP: missing files:', ', '.join(missing))
        return 1
    print('OK: Staging deployment files are present')
    git = run('git', 'rev-parse', '--is-inside-work-tree')
    if git.returncode:
        print('NOTE: Git repository is not initialized. Finish Stage 11A first.')
        return 1
    tracked = run('git', 'ls-files', '--cached', '--full-name')
    if tracked.returncode:
        print('STOP: cannot inspect Git tracked files')
        return 1
    dangerous = [p for p in tracked.stdout.splitlines() if any(r.search(p) for r in REJECT)]
    if dangerous:
        print('STOP: Files already tracked by Git must be removed from index before push:')
        for p in dangerous[:50]:
            print(' -', p)
        print('Suggested approach (preserves local copies): git rm --cached -- <path>')
        return 1
    for p in ('db.sqlite3', '.venv/placeholder'):
        ignored = run('git', 'check-ignore', '-q', p)
        if ignored.returncode:
            print('STOP: .gitignore does not exclude:', p)
            return 1
    print('OK: No database, private uploads or secret files detected among Git tracked paths')
    print('OK: SQLite database and virtual environment are ignored')
    print('NOTE: Review staged file content for hardcoded secrets before pushing.')
    print('NOTE: Staging is not live until YOU connect GitHub and a hosting provider.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
