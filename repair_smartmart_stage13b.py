"""Repair Stage 13B's stale test-object assertion and retry its safe installer.

The production cashier shift service is NOT modified. This patch fixes the test
by refreshing its original Django model instance after the service closes the
shift using a separately fetched database instance.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TEST_FILE = ROOT / "shift_ops" / "tests.py"
INSTALLER = ROOT / "install_smartmart_stage13b.py"
START = b"    def test_closing_twice_or_entry_after_closing_rejected(self):"
END = b"    def test_manager_emergency_close_requires_reason(self):"
OLD = b"        self.assertEqual(sh.expected_cash, Decimal('100.00'))"
REFRESH = b"        sh.refresh_from_db()"


def fail(message: str) -> None:
    raise SystemExit("STAGE 13B REPAIR STOPPED: " + message)


def repair() -> None:
    print("SMARTMART ERP STAGE 13B - CASHIER SHIFT TEST REPAIR", flush=True)
    if not TEST_FILE.is_file() or not INSTALLER.is_file():
        fail("Missing Stage 13B files. Extract the original Stage 13B ZIP into your SmartMartERP project first.")
    raw = TEST_FILE.read_bytes()
    if raw.count(START) != 1 or raw.count(END) != 1 or raw.index(END) <= raw.index(START):
        fail("Tests differ from the supported Stage 13B layout. No files changed.")
    a, b = raw.index(START), raw.index(END)
    block = raw[a:b]
    if block.count(OLD) != 1:
        fail("Expected test assertion not found exactly once. No files changed.")
    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    corrected = REFRESH + nl + OLD
    if corrected in block:
        print("ALREADY PATCHED: Test refreshes the saved shift before checking expected cash.", flush=True)
    else:
        # Keep the repair restricted to one test method and one assertion.
        if REFRESH in block:
            fail("Unexpected existing refresh in the test. No files changed.")
        updated = raw[:a] + block.replace(OLD, corrected, 1) + raw[b:]
        backup_root = Path.home() / "Documents" / "SmartMartERP_Backups"
        backup_dir = backup_root / ("Stage13B_Test_Repair_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        backup_dir.mkdir(parents=True, exist_ok=False)
        shutil.copy2(TEST_FILE, backup_dir / "tests.py.before_repair")
        temporary = TEST_FILE.with_name("tests.py.stage13b_temp")
        try:
            temporary.write_bytes(updated)
            os.replace(temporary, TEST_FILE)
        finally:
            temporary.unlink(missing_ok=True)
        print("PATCHED: Only the failing test assertion was updated.", flush=True)
        print("Private copy of the old test:", backup_dir, flush=True)
    print("RETRYING: python install_smartmart_stage13b.py", flush=True)
    result = subprocess.run([sys.executable, str(INSTALLER)], cwd=ROOT, check=False)
    if result.returncode:
        fail("The Stage 13B installer still reports a problem (exit code "+str(result.returncode)+"). "
             "Copy the new output here. The installer restores settings on failure; do NOT reset the database.")
    print("\nSTAGE 13B REPAIR COMPLETE.")
    print("NEXT: python manage.py test --noinput")
    print("NEXT: python manage.py check")
    print("NEXT: python manage.py runserver 8002")


if __name__ == "__main__":
    repair()
