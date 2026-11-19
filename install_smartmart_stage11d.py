"""Install standalone read-only verification utility without modifying Django/data."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'stage11d_verification' / 'smartmart_stage11d_verify.py'
TARGET = ROOT / 'smartmart_stage11d_verify.py'


def main():
    print('SMARTMART ERP — STAGE 11D STAGING VERIFICATION')
    if not (ROOT / 'manage.py').is_file() or not (ROOT / 'config' / 'settings.py').is_file():
        print('STOP: Extract the package into your EXISTING SmartMartERP project folder.')
        return 2
    if not SOURCE.is_file():
        print('STOP: ZIP incomplete; expected ' + str(SOURCE.relative_to(ROOT)))
        return 2
    code = SOURCE.read_text(encoding='utf-8')
    compile(code, str(SOURCE), 'exec')
    if TARGET.exists():
        if TARGET.read_text(encoding='utf-8') != code:
            print('STOP: An existing customized verification script would be overwritten; no changes made.')
            return 2
        print('Already installed. Existing verification script unchanged.')
        return 0
    try:
        with TARGET.open('x', encoding='utf-8') as f:
            f.write(code)
    except FileExistsError:
        print('STOP: target script appeared during installation; no overwrite performed.')
        return 2
    print('Installed:', TARGET.name)
    print('No Django settings, models, URLs, migrations or business records changed.')
    print('NEXT: python smartmart_stage11d_verify.py --mode local')
    return 0


if __name__ == '__main__':
    sys.exit(main())
