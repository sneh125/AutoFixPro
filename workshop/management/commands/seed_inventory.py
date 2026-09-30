from decimal import Decimal
from django.core.management.base import BaseCommand
from workshop.models import Inventory

DEFAULT_INVENTORY_SEEDS = [
    {"name": "Premium Synthetic Engine Oil (5W-30)", "category": "Fluids", "quantity": 45, "price": Decimal("1200.00"), "image_url": "/static/images/parts/engine_oil.jpg"},
    {"name": "Front Ceramic Brake Pads", "category": "Brakes", "quantity": 18, "price": Decimal("2500.00"), "image_url": "/static/images/parts/brake_pads.jpg"},
    {"name": "High-Flow Oil Filter", "category": "Filters", "quantity": 60, "price": Decimal("350.00"), "image_url": "/static/images/parts/air_filter.jpg"},
    {"name": "Iridium Spark Plug Set (x4)", "category": "Ignition", "quantity": 8, "price": Decimal("1800.00"), "image_url": "/static/images/parts/spark_plugs.jpg"},
    {"name": "Engine Coolant Anti-Freeze (Red, 5L)", "category": "Fluids", "quantity": 25, "price": Decimal("850.00"), "image_url": "/static/images/parts/coolant.jpg"},
    {"name": "Activated Carbon Cabin Air Filter", "category": "Filters", "quantity": 0, "price": Decimal("600.00"), "image_url": "/static/images/parts/cabin_filter.jpg"},
    {"name": "Heavy Duty Maintenance-Free Car Battery 12V", "category": "Electrical", "quantity": 12, "price": Decimal("5500.00"), "image_url": "/static/images/parts/battery.jpg"},
    {"name": "Aerodynamic Wiper Blade Pair", "category": "Accessories", "quantity": 30, "price": Decimal("900.00"), "image_url": "/static/images/parts/wiper_blades.jpg"},
    {"name": "DOT 4 High Performance Brake Fluid (1L)", "category": "Fluids", "quantity": 40, "price": Decimal("450.00"), "image_url": "/static/images/parts/brake_fluid.jpg"},
    {"name": "Engine Timing Belt Kit", "category": "Engine", "quantity": 6, "price": Decimal("4200.00"), "image_url": "/static/images/parts/timing_belt.jpg"},
]


class Command(BaseCommand):
    help = "Seeds initial spare parts catalog into Inventory without mutating data on GET requests"

    def handle(self, *args, **options):
        created_count = 0
        for item in DEFAULT_INVENTORY_SEEDS:
            obj, created = Inventory.objects.get_or_create(
                name=item["name"],
                defaults={
                    "category": item["category"],
                    "quantity": item["quantity"],
                    "price": item["price"],
                    "image_url": item["image_url"],
                }
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created: {item['name']}"))
            else:
                self.stdout.write(f"Already exists: {item['name']}")

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {created_count} new inventory items."))
