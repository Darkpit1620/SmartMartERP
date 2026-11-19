#!/usr/bin/env python3
"""Read-only staging verification for SmartMart ERP.

Modes:
  local:  check local files and Git exclusions; optionally run Django checks/tests.
  server: verify runtime Django, PostgreSQL and migrations in Render Shell.
  remote: make anonymous GET requests to the HTTPS staging site.

Does not log in, migrate, modify data, or create real payments/transactions.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
STAGING_MODULE = 'config.settings_render_staging'
REQUIRED_FILES = (
    'manage.py', 'config/settings.py', 'config/settings_production.py',
    'config/settings_render_staging.py', 'render_staging_build.sh',
    'render_staging_start.sh', 'deployment_stage10d/requirements-production.txt',
)
SECRET_PATH = re.compile(
    r'(^|/)(?:\.env(?:\.[^/]*)?|\.venv|media|staticfiles|__pycache__|'
    r'backups?|[^/]*_backups)(?:/|$)|'
    r'\.(?:sqlite3?|db|pem|key)$|(^|/)db\.sqlite3(?:-[^/]*)?$',
    re.I,
)


class Report:
    def __init__(self):
        self.fails = 0
        self.reviews = 0

    def pass_(self, text):
        print('  [PASS] ' + text)

    def review(self, text):
        self.reviews += 1
        print('  [REVIEW] ' + text)

    def fail(self, text):
        self.fails += 1
        print('  [FAIL] ' + text)

    def finish(self):
        print(f'\nSUMMARY: {self.fails} failures; {self.reviews} review items.')
        if self.fails:
            print('RESULT: NOT READY. Resolve failures before continuing.')
            return 2
        if self.reviews:
            print('RESULT: CHECKS PASSED WITH MANUAL FOLLOW-UP REQUIRED.')
            return 0
        print('RESULT: AUTOMATED CHECKS PASSED (NOT A SECURITY CERTIFICATION).')
        return 0


def command(*parts, env=None):
    return subprocess.run(parts, cwd=ROOT, env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=180)


def local_mode(report, full_tests=False):
    print('SMARTMART STAGE 11D — LOCAL READINESS CHECK (READ-ONLY)\n')
    missing = [f for f in REQUIRED_FILES if not (ROOT / f).is_file()]
    if missing:
        report.fail('Missing Stage 10D/11B prerequisites: ' + ', '.join(missing))
        return
    report.pass_('Staging config, Render scripts, and production requirements present')

    try:
        result = command('git', 'rev-parse', '--is-inside-work-tree')
    except (FileNotFoundError, subprocess.TimeoutExpired):
        report.fail('Git is not available. Install Git for Windows first.')
        return
    if result.returncode != 0 or result.stdout.strip() != 'true':
        report.fail('Project is not yet in a Git repository; complete Stage 11A')
        return
    report.pass_('Git repository detected')

    tracked = command('git', 'ls-files', '--cached', '--full-name')
    if tracked.returncode:
        report.fail('Git tracked-file listing failed')
        return
    risky = [f for f in tracked.stdout.splitlines() if SECRET_PATH.search(f.replace('\\', '/'))]
    if risky:
        report.fail('Potentially private files are tracked in Git: ' + ', '.join(risky[:8]))
        report.review('Remove from Git index safely with git rm --cached -- <file> (not from disk)')
    else:
        report.pass_('No common secret, backup, SQLite, or media file paths tracked in Git')

    for f in ['db.sqlite3', '.env', '.venv/placeholder', 'media/placeholder']:
        ignored = command('git', 'check-ignore', '-q', f)
        if ignored.returncode:
            report.fail('.gitignore does not protect ' + f)
        else:
            report.pass_('.gitignore excludes ' + f)

    remote = command('git', 'remote', '-v')
    if remote.returncode != 0 or not remote.stdout.strip():
        report.review('No Git remote configured; connect a PRIVATE repository before hosting')
    else:
        report.pass_('Git remote is configured (URL intentionally not printed)')

    if not (ROOT / 'smartmart_backup.py').exists():
        report.review('Verified local backup script missing')
    else:
        report.pass_('Local backup command is available (a backup was not run)')

    checks = command(sys.executable, 'manage.py', 'check')
    if checks.returncode:
        report.fail('Local Django check failed; examine output: ' + (checks.stdout + checks.stderr)[-1000:])
    else:
        report.pass_('Local Django system check passed')

    if full_tests:
        print('  [INFO] Running full Django tests in a temporary TEST database...')
        try:
            tests = subprocess.run([sys.executable, 'manage.py', 'test', '--noinput'],
                                   cwd=ROOT, check=False, timeout=900)
            if tests.returncode:
                report.fail('Full Django test suite failed')
            else:
                report.pass_('Full Django tests passed')
        except subprocess.TimeoutExpired:
            report.fail('Full Django tests exceeded 15 minutes')
    else:
        report.review('Full local tests not run; add --full-tests when convenient')

    report.review('An online staging URL has not been checked in local mode')


def server_mode(report):
    print('SMARTMART STAGE 11D — RENDER SERVER CHECK (READ-ONLY)\n')
    if not (ROOT / 'manage.py').is_file():
        report.fail('Run this from the installed SmartMartERP root directory')
        return
    if os.environ.get('DJANGO_SETTINGS_MODULE') != STAGING_MODULE:
        report.fail('DJANGO_SETTINGS_MODULE must equal ' + STAGING_MODULE)
        return
    report.pass_('Dedicated staging settings module selected')
    for name in ('DATABASE_URL', 'SMARTMART_SECRET_KEY', 'SMARTMART_ALLOWED_HOSTS',
                 'SMARTMART_CSRF_TRUSTED_ORIGINS', 'SMARTMART_MEDIA_ROOT'):
        if os.environ.get(name, '').strip():
            report.pass_(name + ' is supplied (value hidden)')
        else:
            report.fail(name + ' is missing')
    if report.fails:
        return

    try:
        import django
        django.setup()
        from django.conf import settings
        from django.db import connections
    except Exception as exc:
        report.fail('Django setup failed: ' + str(exc).splitlines()[0][:250])
        return

    if settings.DEBUG is False:
        report.pass_('DEBUG=False')
    else:
        report.fail('DEBUG must be False on internet-connected staging')
    for k in ('SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE'):
        if getattr(settings, k, False) is True:
            report.pass_(k + '=True')
        else:
            report.fail(k + ' must be True')
    hosts = settings.ALLOWED_HOSTS
    if hosts and '*' not in hosts and all(h.strip() for h in hosts):
        report.pass_('ALLOWED_HOSTS contains explicit hosts')
    else:
        report.fail('ALLOWED_HOSTS is missing or overly broad')
    engine = settings.DATABASES.get('default', {}).get('ENGINE')
    if engine == 'django.db.backends.postgresql':
        report.pass_('Default Django database is PostgreSQL')
    else:
        report.fail('Default database is not PostgreSQL; refuse public staging with SQLite')
    media = Path(str(settings.MEDIA_ROOT))
    if media == Path('/var/data/media'):
        report.pass_('Media path points inside the expected /var/data persistent disk')
        if not Path('/var/data').exists():
            report.fail('Persistent disk mount /var/data does not exist on this server')
        elif not os.access('/var/data', os.W_OK):
            report.review('Persistent disk may not be writable by the web process')
        else:
            report.pass_('Persistent disk mount directory exists and is writable')
    else:
        report.fail('MEDIA_ROOT does not match the configured /var/data/media staging mount')

    if engine == 'django.db.backends.postgresql':
        try:
            with connections['default'].cursor() as cur:
                cur.execute('SELECT 1')
                if cur.fetchone()[0] == 1:
                    report.pass_('PostgreSQL connection and read-only SELECT 1 succeeded')
        except Exception as exc:
            report.fail('PostgreSQL connection/read failed: ' + type(exc).__name__)

    for argv, name in [
        (('check', '--settings=' + STAGING_MODULE), 'Django staging configuration check'),
        (('migrate', '--check', '--noinput', '--settings=' + STAGING_MODULE),
         'All migrations applied (no migration executed)'),
    ]:
        try:
            proc = command(sys.executable, 'manage.py', *argv)
            if proc.returncode:
                report.fail(name + ' failed: ' + (proc.stdout + proc.stderr)[-700:])
            else:
                report.pass_(name)
        except subprocess.TimeoutExpired:
            report.fail(name + ' timed out')

    try:
        deploy = command(sys.executable, 'manage.py', 'check', '--deploy',
                         '--settings=' + STAGING_MODULE)
        output = deploy.stdout + deploy.stderr
        warnings = sorted(set(re.findall(r'\bsecurity\.(?:W|E)\d{3}\b', output)))
        critical = [w for w in warnings if w not in {'security.W004', 'security.W008'}]
        if critical or deploy.returncode:
            report.fail('Unreviewed Django deployment findings: ' + ', '.join(critical or warnings) +
                        '. Inspect manage.py check --deploy output on server')
        else:
            report.pass_('No unexpected Django deployment security findings')
        if 'security.W008' in warnings:
            report.review('Django HTTPS redirect is disabled; confirm Render edge redirects HTTP to HTTPS')
        if 'security.W004' in warnings:
            report.review('HSTS not enabled; keep staging separate from production')
    except subprocess.TimeoutExpired:
        report.fail('Django deployment check timed out')
    report.review('Verify Render PostgreSQL backups and restore separately; SQLite backup does NOT cover PostgreSQL')
    report.review('Verify payment provider webhooks, authorized media access and KRA eTIMS before live use')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, timeout=12):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'SmartMart-Staging-ReadOnly-Verification/1.0',
        'Accept': 'text/html,*/*;q=0.8',
    }, method='GET')
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as r:
            return r.status, r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.headers


def remote_mode(report, input_url, timeout=12):
    print('SMARTMART STAGE 11D — EXTERNAL HTTPS SMOKE CHECK (ANONYMOUS, READ-ONLY)\n')
    if not input_url:
        report.fail('Provide --url https://your-actual-staging-service.onrender.com')
        return
    try:
        parsed = urllib.parse.urlsplit(input_url)
        port = parsed.port
    except ValueError:
        report.fail('Malformed HTTPS URL or port in --url')
        return
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or port not in (None, 443) or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        report.fail('Use a bare HTTPS origin only, with no login details or paths')
        return
    origin = 'https://' + parsed.hostname + (':' + str(port) if port else '')
    report.pass_('Staging origin uses HTTPS')
    try:
        status, headers = fetch(origin + '/', timeout)
        if status == 200:
            report.pass_('Staging homepage returned HTTP 200')
        elif status in (401, 403):
            report.review('Homepage is restricted to authorized users (HTTP ' + str(status) + ')')
        elif status in (301, 302, 303, 307, 308):
            location = headers.get('Location', '')
            resolved = urllib.parse.urljoin(origin + '/', location)
            if urllib.parse.urlsplit(resolved).scheme != 'https':
                report.fail('Homepage redirects to an HTTP (non-HTTPS) URL')
            else:
                report.review('Homepage redirects over HTTPS; verify final page manually')
        else:
            report.fail('Homepage returned HTTP ' + str(status))
        for k in ('X-Content-Type-Options', 'X-Frame-Options', 'Referrer-Policy'):
            if headers.get(k):
                report.pass_(k + ' header present')
            else:
                report.review(k + ' header not present on homepage response')
        if headers.get('Strict-Transport-Security'):
            report.pass_('HSTS header present')
        else:
            report.review('HSTS not present (acceptable for initial staging, not final launch)')
        cookies = (headers.get_all('Set-Cookie', []) if hasattr(headers, 'get_all')
                   else ([headers['Set-Cookie']] if 'Set-Cookie' in headers else []))
        for cookie in cookies:
            if re.search(r'(?i)^\s*(?:sessionid|csrftoken)\s*=', cookie):
                if not re.search(r'(?i)(?:^|;)\s*Secure\s*(?:;|$)', cookie):
                    report.fail('Authentication/CSRF cookie was sent without Secure attribute')
                else:
                    report.pass_('Authentication/CSRF cookie has Secure attribute')
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        report.fail('Cannot reach HTTPS staging homepage: ' + type(exc).__name__)
        return

    for path in ('/portal/admin/', '/operations/', '/transaction-tests/'):
        try:
            status, headers = fetch(origin + path, timeout)
            if status == 200:
                report.fail('Anonymous request to ' + path + ' received HTTP 200; check access controls')
            elif status in (301, 302, 303, 307, 308):
                redirect = urllib.parse.urljoin(origin + path, headers.get('Location', ''))
                redirect_parts = urllib.parse.urlsplit(redirect)
                if redirect_parts.scheme == 'https' and redirect_parts.hostname == parsed.hostname:
                    report.pass_(path + ' redirects anonymous visitors on HTTPS (HTTP ' + str(status) + ')')
                else:
                    report.fail(path + ' redirects to unexpected host or insecure URL')
            elif status in (401, 403):
                report.pass_(path + ' denies anonymous visitors (HTTP ' + str(status) + ')')
            elif status == 404:
                report.review(path + ' returned 404; verify this module is installed and routed')
            else:
                report.fail(path + ' returned unexpected HTTP ' + str(status))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            report.fail('Request failed for ' + path + ': ' + type(exc).__name__)

    report.review('External checks cannot prove database persistence, permissions for signed-in users or payment correctness')


def make_parser():
    p = argparse.ArgumentParser(description='Read-only SmartMart ERP staging verification')
    p.add_argument('--mode', choices=('local', 'server', 'remote'), default='local')
    p.add_argument('--url', help='Remote mode: actual HTTPS staging origin; NO password or URL query')
    p.add_argument('--full-tests', action='store_true', help='Local mode only: run all Django tests in temporary test DB')
    p.add_argument('--timeout', type=int, default=12, help='Remote request timeout in seconds')
    return p


def main(argv=None):
    args = make_parser().parse_args(argv)
    if args.full_tests and args.mode != 'local':
        print('ERROR: --full-tests is permitted only in local mode, not on a staging server.')
        return 2
    if args.timeout < 1 or args.timeout > 60:
        print('ERROR: timeout must be 1 to 60 seconds')
        return 2
    report = Report()
    if args.mode == 'local':
        local_mode(report, args.full_tests)
    elif args.mode == 'server':
        server_mode(report)
    else:
        remote_mode(report, args.url, args.timeout)
    return report.finish()


if __name__ == '__main__':
    raise SystemExit(main())
