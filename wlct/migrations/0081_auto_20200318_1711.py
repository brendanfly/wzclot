# Generated by Django 2.1.4 on 2020-03-19 00:11

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wlct', '0080_auto_20200318_1624'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='promotionalrelegationleaguedivision',
            name='season',
        ),
        migrations.AddField(
            model_name='clanleaguedivision',
            name='pr_season',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='wlct.PromotionalRelegationLeagueSeason'),
        ),
        migrations.DeleteModel(
            name='PromotionalRelegationLeagueDivision',
        ),
    ]
