"""python manage.py smartmart_audit [--json] [--strict]"""
import json
from django.core.management.base import BaseCommand, CommandError
from operations.diagnostics import collect_snapshot, security_flags, findings


class Command(BaseCommand):
    help = 'Read-only SmartMart operational audit and deployment configuration review.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Print JSON without private account information.')
        parser.add_argument('--strict', action='store_true', help='Exit nonzero if severe data faults or deployment settings are incomplete.')

    def handle(self, *args, **options):
        data = collect_snapshot()
        flags = security_flags()
        notes = findings(data)
        result = {
            'metrics': data, 'security': flags, 'findings': notes,
            'deployment_ready': all(f['ok'] for f in flags)
            and not any(f['severity'] == 'critical' for f in notes),
        }
        if options['json']:
            self.stdout.write(json.dumps(result, indent=2))
        else:
            self.stdout.write('SMARTMART ERP: READ-ONLY OPERATIONS AUDIT')
            for name, value in data.items():
                self.stdout.write(f'  {name.replace("_", " ").title()}: {value}')
            self.stdout.write('\nDEPLOYMENT SETTINGS')
            for flag in flags:
                self.stdout.write(f'  [{"PASS" if flag["ok"] else "ACTION"}] {flag["label"]}')
            self.stdout.write('\nDATA REVIEW')
            if not notes:
                self.stdout.write('  No flagged data records.')
            for item in notes:
                self.stdout.write(f'  [{item["severity"].upper()}] {item["count"]} — {item["label"]}')
            self.stdout.write('\nThese checks are not an external security audit or payment reconciliation.')
        if options['strict'] and not result['deployment_ready']:
            raise CommandError('Audit found items that block production readiness.')
