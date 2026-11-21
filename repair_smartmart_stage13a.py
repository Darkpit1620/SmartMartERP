"""Safe Stage 13A test-token repair for the existing SmartMart ERP project.

Fixes only the overlong checkout token in returns_ops/tests.py, then retries
its existing installer. Does not touch stock, payments or SQLite directly.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TESTS = ROOT / 'returns_ops' / 'tests.py'
ORIGINAL_INSTALLER = ROOT / 'install_smartmart_stage13a.py'

OLD = "token='stage13-' + str(self._testMethodName)"
NEW = "token='stage13-' + hashlib.sha256(self._testMethodName.encode('utf-8')).hexdigest()[:32]"


def main():
    print('SMARTMART ERP STAGE 13A — TEST-TOKEN REPAIR', flush=True)
    if not TESTS.is_file() or not ORIGINAL_INSTALLER.is_file():
        raise SystemExit('Missing Stage 13A files. Extract the original Stage 13A ZIP in SmartMartERP first.')

    original = TESTS.read_text(encoding='utf-8')
    if OLD in original:
        if original.count(OLD) != 1:
            raise SystemExit('Unexpected duplicate token code. No changes made.')
        if 'import hashlib' not in original:
            if 'from decimal import Decimal\n' not in original:
                raise SystemExit('Unexpected test imports. No changes made.')
            updated = original.replace('from decimal import Decimal\n',
                                       'from decimal import Decimal\nimport hashlib\n', 1)
        else:
            updated = original
        updated = updated.replace(OLD, NEW, 1)
        ast.parse(updated, filename=str(TESTS))
        # Keep a local copy in the existing private backup folder, outside Git.
        # Do not create or modify the SQLite database.
        private = Path.home() / 'Documents' / 'SmartMartERP_Backups' / 'stage13a_tests_before_hotfix.py'
        private.parent.mkdir(parents=True, exist_ok=True)
        if not private.exists():
            private.write_text(original, encoding='utf-8')
        TESTS.write_text(updated, encoding='utf-8')
        print('PATCHED: returns_ops/tests.py (test checkout tokens are now 40 characters).', flush=True)
    elif NEW in original:
        print('ALREADY PATCHED: no duplicate changes.', flush=True)
    else:
        raise SystemExit('The tests file differs from the expected Stage 13A version. No changes made.')

    corrected = TESTS.read_text(encoding='utf-8')
    ast.parse(corrected, filename=str(TESTS))
    assert NEW in corrected and 'import hashlib' in corrected
    names = re.findall(r'^    def (test_\w+)\(', corrected, flags=re.MULTILINE)
    if not names:
        raise SystemExit('No test methods were detected. Stopping.')
    import hashlib
    for name in names:
        token = 'stage13-' + hashlib.sha256(name.encode('utf-8')).hexdigest()[:32]
        if len(token) > 64:
            raise SystemExit('Generated test token is over 64 characters. Stopping.')
    print('CHECK PASSED: generated tokens fit the POS 64-character limit.', flush=True)

    print('RETRYING: original Stage 13A installer and its Django tests...', flush=True)
    result = subprocess.run([sys.executable, str(ORIGINAL_INSTALLER)], cwd=ROOT)
    if result.returncode:
        raise SystemExit(f'Stage 13A installation still needs attention (exit {result.returncode}). '
                         'Do not delete or reset your database. Share the new terminal output.')
    print('\nSTAGE 13A REPAIR AND INSTALLATION COMPLETE.', flush=True)
    print('NEXT: python manage.py test --noinput', flush=True)


if __name__ == '__main__':
    main()
