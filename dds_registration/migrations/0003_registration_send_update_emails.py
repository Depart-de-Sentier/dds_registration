# Generated by Django 5.0.3 on 2024-04-06 20:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dds_registration', '0002_remove_event_refund_window_days_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='registration',
            name='send_update_emails',
            field=models.BooleanField(default=False),
        ),
    ]