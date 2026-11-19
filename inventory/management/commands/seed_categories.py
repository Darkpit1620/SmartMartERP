from django.core.management.base import BaseCommand
from inventory.models import Category

CATEGORIES = [
    "Food & Groceries", "Fresh Produce", "Bakery", "Dairy & Eggs", "Meat & Seafood",
    "Beverages", "Snacks & Confectionery", "Household & Cleaning", "Personal Care",
    "Baby Products", "Electronics", "Stationery & School", "Clothing & Textiles",
    "Hardware & Home", "Pet Supplies", "Other",
]


class Command(BaseCommand):
    help = "Add common supermarket product categories without creating example products."

    def handle(self, *args, **options):
        created = 0
        for name in CATEGORIES:
            _, was_created = Category.objects.get_or_create(name=name)
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Product categories ready: {len(CATEGORIES)} ({created} new)."))
