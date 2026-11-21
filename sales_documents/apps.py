from django.apps import AppConfig


class SalesDocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sales_documents'
    verbose_name = 'Sales receipts and commercial invoices'
