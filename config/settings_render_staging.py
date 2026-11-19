"""Render staging overrides of SmartMart's Stage 10D secure settings.

Render terminates HTTPS at the platform edge and redirects plain HTTP there.
Leaving Django's own redirect disabled avoids reverse-proxy redirect loops.
This is ONLY for Render staging, never a substitute for production review.
"""
from .settings_production import *  # noqa: F401,F403

SECURE_SSL_REDIRECT = False  # Render enforces HTTPS before Django receives traffic.
SECURE_PROXY_SSL_HEADER = None  # Do not trust unsanitized forwarded headers.
SECURE_HSTS_SECONDS = 0  # Begin HSTS rollout only after verified deployment.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
