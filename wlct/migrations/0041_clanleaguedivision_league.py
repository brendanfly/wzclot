# Generated by Django 2.1.4 on 2019-12-09 18:48

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wlct', '0040_tournament_tournament_logs'),
    ]

    operations = [
        migrations.AddField(
            model_name='clanleaguedivision',
            name='league',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='wlct.ClanLeagueTournament'),
        ),
    ]
