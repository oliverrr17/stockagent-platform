from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0003_portfolioperformancesnapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="SecurityPriceSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stock_code", models.CharField(db_index=True, max_length=20)),
                ("stock_name", models.CharField(blank=True, max_length=100)),
                ("market", models.CharField(choices=[("A_STOCK", "A股"), ("HK_STOCK", "港股")], max_length=10)),
                ("trade_date", models.DateField(db_index=True)),
                ("close_price", models.DecimalField(decimal_places=4, max_digits=12)),
                ("previous_close", models.DecimalField(decimal_places=4, max_digits=12)),
                ("open_price", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True)),
                ("high_price", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True)),
                ("low_price", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True)),
                ("volume", models.DecimalField(blank=True, decimal_places=4, max_digits=20, null=True)),
                ("amount", models.DecimalField(blank=True, decimal_places=4, max_digits=20, null=True)),
                ("source", models.CharField(max_length=50)),
                ("degraded", models.BooleanField(default=False)),
                ("degraded_reason", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["trade_date", "stock_code"],
                "unique_together": {("stock_code", "market", "trade_date")},
            },
        ),
    ]
