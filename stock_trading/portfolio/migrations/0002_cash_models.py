from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CashAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("currency", models.CharField(choices=[("CNY", "人民币"), ("HKD", "港币")], max_length=3, unique=True)),
                ("label", models.CharField(blank=True, max_length=50)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["currency"]},
        ),
        migrations.CreateModel(
            name="FXRate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("base_currency", models.CharField(max_length=3)),
                ("quote_currency", models.CharField(max_length=3)),
                ("rate_date", models.DateField(db_index=True)),
                ("rate", models.DecimalField(decimal_places=6, max_digits=12)),
                ("source", models.CharField(max_length=50)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-rate_date"], "unique_together": {("base_currency", "quote_currency", "rate_date")}},
        ),
        migrations.CreateModel(
            name="CashFlow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("direction", models.CharField(choices=[("DEPOSIT", "入金"), ("WITHDRAWAL", "出金")], max_length=10)),
                ("amount", models.DecimalField(decimal_places=4, max_digits=18)),
                ("occurred_at", models.DateTimeField(db_index=True)),
                ("note", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("cash_account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="flows", to="portfolio.cashaccount")),
            ],
            options={"ordering": ["-occurred_at", "-id"]},
        ),
    ]
