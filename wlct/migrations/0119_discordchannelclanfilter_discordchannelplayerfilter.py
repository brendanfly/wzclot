# Generated by Django 2.2.4 on 2020-05-02 01:22

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wlct', '0118_auto_20200430_1325'),
    ]

    operations = [
        migrations.CreateModel(
            name='DiscordChannelPlayerFilter',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('link', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='wlct.DiscordChannelTournamentLink')),
                ('player', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='wlct.Player')),
            ],
        ),
        migrations.CreateModel(
            name='DiscordChannelClanFilter',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('clan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='wlct.Clan')),
                ('link', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='wlct.DiscordChannelTournamentLink')),
            ],
        ),
    ]
