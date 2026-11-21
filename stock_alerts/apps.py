from django.apps import AppConfig


class StockAlertsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stock_alerts'
    verbose_name = 'Branch Low-Stock Alerts'
