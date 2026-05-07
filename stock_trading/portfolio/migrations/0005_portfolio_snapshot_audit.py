from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0004_securitypricesnapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="portfolioperformancesnapshot",
            name="audit_status",
            field=models.CharField(
                choices=[("FINAL", "Final"), ("PROVISIONAL", "Provisional")],
                default="PROVISIONAL",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="portfolioperformancesnapshot",
            name="computed_daily_pnl_cny",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name="portfolioperformancesnapshot",
            name="external_flow_cny",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=18),
        ),
        migrations.CreateModel(
            name="PositionDailyContributionSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snapshot_date", models.DateField(db_index=True)),
                ("stock_code", models.CharField(db_index=True, max_length=20)),
                ("stock_name", models.CharField(blank=True, max_length=100)),
                ("market", models.CharField(choices=[("A_STOCK", "A股"), ("HK_STOCK", "港股")], max_length=10)),
                ("start_quantity", models.IntegerField(default=0)),
                ("end_quantity", models.IntegerField(default=0)),
                ("previous_close", models.DecimalField(decimal_places=4, max_digits=12)),
                ("latest_price", models.DecimalField(decimal_places=4, max_digits=12)),
                ("trade_cash_delta", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                ("daily_pnl_native", models.DecimalField(decimal_places=4, max_digits=18)),
                ("daily_pnl_cny", models.DecimalField(decimal_places=4, max_digits=18)),
                ("fx_rate", models.DecimalField(decimal_places=6, default=1, max_digits=12)),
                ("price_source", models.CharField(max_length=50)),
                ("source_trade_date", models.DateField(blank=True, null=True)),
                ("degraded", models.BooleanField(default=False)),
                ("degraded_reason", models.CharField(blank=True, max_length=200)),
                (
                    "audit_status",
                    models.CharField(
                        choices=[("FINAL", "Final"), ("PROVISIONAL", "Provisional")],
                        default="PROVISIONAL",
                        max_length=12,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["snapshot_date", "market", "stock_code"],
                "unique_together": {("snapshot_date", "stock_code", "market")},
            },
        ),
    ]
