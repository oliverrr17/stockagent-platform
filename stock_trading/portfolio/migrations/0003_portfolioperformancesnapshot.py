from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0002_cash_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="PortfolioPerformanceSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snapshot_date", models.DateField(db_index=True, unique=True)),
                ("total_assets_cny", models.DecimalField(decimal_places=4, max_digits=18)),
                ("total_return_cny", models.DecimalField(decimal_places=4, max_digits=18)),
                ("daily_return_pct", models.DecimalField(decimal_places=4, max_digits=12)),
                ("monthly_return_pct", models.DecimalField(decimal_places=4, max_digits=12)),
                ("yearly_return_pct", models.DecimalField(decimal_places=4, max_digits=12)),
                ("cumulative_return_pct", models.DecimalField(decimal_places=4, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["snapshot_date"]},
        ),
    ]
