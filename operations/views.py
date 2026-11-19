from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_GET
from django.shortcuts import render
from .diagnostics import collect_snapshot, security_flags, findings


@login_required
@require_GET
def overview(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied('System readiness reports are restricted to head-office superusers.')
    data = collect_snapshot()
    flags = security_flags()
    return render(request, 'operations/overview.html', {
        'data': data, 'flags': flags, 'findings': findings(data),
        'deployment_ready': all(item['ok'] for item in flags),
    })
