from discord.ext import commands, tasks
from django.core.management.base import BaseCommand
from django.conf import settings
import datetime
from django.utils import timezone
from wlct.tournaments import RealTimeLadder, TournamentGame, get_team_data_sameline, get_team_data_no_clan
from wlct.models import Engine, Player, DiscordUser
import asyncio
import discord
import os

description = '''An example bot to showcase the discord.ext.commands extension
module.

There are a number of utility commands being showcased here.'''
def get_cmd_prefix():
    if not settings.DEBUG:
        return "bb!"
    else:
        return "bt!"

EXTENSIONS = ['wlct.cogs.common', 'wlct.cogs.clot', 'wlct.cogs.help', 'wlct.cogs.ladders', 'wlct.cogs.tasks']

class WZBot(commands.AutoShardedBot):

    def __init__(self):
        self.prefix = get_cmd_prefix()
        print("[PREFIX]: {}".format(self.prefix))
        super().__init__(command_prefix=str(self.prefix), reconnect=True, case_insensitive=True)

        # initialize some bot state
        self.embed_color = 0xFE8000
        self.cmdUsage = {}
        self.cmdUsers = {}
        self.guildUsage = {}
        self.rtl_channels = []
        self.clan_league_channels = []
        self.mtc_channels = []
        self.critical_error_channels = []
        self.game_log_channels = []
        self.last_task_run = timezone.now()
        self.cache_queue = []
        self.clot_server = None
        self.executions = 0

        # deltas for when the bot does stuff
        self.discord_link_text = "Your discord account is not linked to the CLOT. Please see <http://wztourney.herokuapp.com/me/> for instructions."
        self.discord_link_text_user = "That user's discord account is not linked to the CLOT."

        for ext in EXTENSIONS:
            self.load_extension(ext)
            print("Loaded extension: {}".format(ext))

    @property
    def owner(self):
        return self.get_user(self.owner_id)

    async def on_disconnect(self):
        for channel in self.rtl_channels:
            # await channel.send("Updating my code...be right back...")
            pass

    async def on_message(self, msg):
        if not self.is_ready() or msg.author.bot:
            return

        await self.process_commands(msg)

    async def on_member_join(self, member):
        cog = self.get_cog("tasks")
        if cog:
            await cog.process_member_join(member.id)

    def get_embed(self, user):
        emb = discord.Embed(color=self.embed_color)
        emb.set_author(icon_url=user.avatar_url, name=user)
        emb.set_footer(text="Bot created and maintained by -B#0292")

        return emb

    def get_default_embed(self):
        return self.embed(self)

    async def on_ready(self):
        print(f'[CONNECT] Logged in as:\n{self.user} (ID: {self.user.id})\n')

        # cache all the guilds we're in when we login and the real-time-ladder channels
        for guild in self.guilds:
            if guild.name == "-B's CLOT":
                print("Found -B's CLOT, caching...id: {}".format(guild.id))
                self.clot_server = guild
            for channel in guild.channels:
                if channel.name == "real-time-ladder" or channel.name == "real_time_ladder":
                    print("Caching RTL channel in guild: {}".format(guild.name))
                    self.rtl_channels.append(channel)
                elif channel.name == "monthly-template-circuit" or channel.name == "monthly_template_circuit":
                    print("Caching MTC channel in guild: {}".format(guild.name))
                    self.mtc_channels.append(channel)
                elif channel.name == "clan-league-bot-chat" or channel.name == "clan_league_bot_chat":
                    print("Caching CL channel in guild: {}".format(guild.name))
                    self.clan_league_channels.append(channel)
                elif channel.name == "critical-errors":
                    print("Caching Critical Error Channel in guild: {}".format(guild.name))
                    self.critical_error_channels.append(channel)

        if not hasattr(self, 'uptime'):
            self.uptime = timezone.now()

    def get_channel_list(self):
        return self.rtl_channels

    async def update_progress(self, message, pct):
        # shows and updates the same message displaying progress for longer running tasks
        await message.edit(content="{} %".format(pct))

class Command(BaseCommand):
    help = "Runs the CLOT Bot"
    def handle(self, *args, **options):
        if settings.DEBUG:
            bot = WZBot()
            bot.run(os.environ['WZ_TEST_BOT_TOKEN'])
        else:
            bot = WZBot()
            bot.run(os.environ['WZ_BOT_TOKEN'])
