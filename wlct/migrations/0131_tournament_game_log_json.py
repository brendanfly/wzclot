# Generated by Django 3.1.4 on 2022-02-24 04:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wlct', '0130_auto_20210124_1052'),
    ]

    operations = [
        migrations.AddField(
            model_name='tournament',
            name='game_log_json',
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
    ]
