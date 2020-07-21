from discord.ext import commands, tasks
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from wlct.logging import log_exception, Logger, LogLevel
import time, threading, sys, os, discord, traceback, json

description = '''An example bot to showcase the discord.ext.commands extension
module.

There are a number of utility commands being showcased here.'''
def get_cmd_prefix():
    if not settings.DEBUG:
        return "bb!"
    else:
        return "bt!"

EXTENSIONS = ['wlct.cogs.common', 'wlct.cogs.clot', 'wlct.cogs.clotbook', 'wlct.cogs.help', 'wlct.cogs.ladders', 'wlct.cogs.tasks']

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
        self.process_queue = []
        self.clot_server = None
        self.executions = 0
        self.performance_counter = False
        self.running = True

        # deltas for when the bot does stuff
        self.discord_link_text = "Your discord account is not linked to the CLOT. Please see <http://wzclot.eastus.cloudapp.azure.com/me/> for instructions."
        self.discord_link_text_user = "That user's discord account is not linked to the CLOT."

        self.last_known_commit = ""

        for ext in EXTENSIONS:
            self.load_extension(ext)
            print("Loaded extension: {}".format(ext))

    def flush(self):
        while True and not self.shutdown:
            sys.stdout.flush()
            sys.stdout.flush()
            time.sleep(5)

    def handle_git(self):
        while not self.shutdown:
            try:
                # grab the latest commit the database knows about
                logger = Logger.objects.filter(level=LogLevel.webhook)[:1]  # only care about the last one
                if logger:
                    logger = logger[0]
                    if logger.msg is not None and len(logger.msg) > 0:
                        webhook_dict = json.loads('''{}'''.format(logger.msg))
                        if 'ref' in webhook_dict and 'before' in webhook_dict and 'after' in webhook_dict:
                            if webhook_dict['ref'] == 'refs/heads/master':
                                if webhook_dict['after'] != self.last_known_commit and self.last_known_commit is not "":
                                    print("[ENGINE]: Found commit to the master branch...processing")
                                    print("Commit is new, shutting down engine")
                                    self.shutdown = True
                                self.last_known_commit = webhook_dict['after']
                                print(
                                    "[ENGINE] Last known good commit: {}".format(self.last_known_commit))
            except:
                print(traceback.format_exc())
            finally:
                # sleep for 30 seconds before checking again
                print("Sleeping for 10 seconds, running? {}. Last known commit: {}".format(self.running,
                                                                                           self.last_known_commit))
                time.sleep(10)
                sys.stdout.flush()
            if self.shutdown is True:
                cog = self.get_cog("tasks")
                if cog:
                    cog.bg_task.stop()
                self.close()
                sys.exit(0)

    def perf_counter(self, msg):
        if self.performance_counter:
            print(msg)

    @property
    def owner(self):
        return self.get_user(self.owner_id)

    async def on_disconnect(self):
        for channel in self.critical_error_channels:
            print("Disconnecting...trying to restart")

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
        return self.get_embed(self.user)

    async def on_ready(self):
        try:
            print(f'[CONNECT] Logged in as:\n{self.user} (ID: {self.user.id})\n')

            # cache all the guilds we're in when we login and the real-time-ladder channels
            for guild in self.guilds:
                if guild.name == "-B's CLOT":
                    print("Found -B's CLOT, caching...id: {}".format(guild.id))
                    self.clot_server = guild
                for channel in guild.channels:
                    if channel.name == "real-time-ladder" or channel.name == "real_time_ladder":
                        print("Found RTL Channel in guild: {}".format(guild.name))
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

            self.shutdown = False
            print("Creating communication thread...")
            self.comm_thread = threading.Thread(target=self.handle_git)
            self.comm_thread.start()

            print("Creating flushing thread")
            self.flush_thread = threading.Thread(target=self.flush)
            self.flush_thread.start()

        except Exception as e:
            log_exception()

    async def update_progress(self, edit_message, message_text, pct):
        # shows and updates the same message displaying progress for longer running tasks
        await edit_message.edit(content="{}...{} %".format(message_text, pct))

    def embed_list(self, embed, field_name, list, inline=False):
        total_chars = 0
        field_values = []
        for item in list:
            new_total_chars = total_chars + len(item)
            #print("New Total Chars: {}".format(new_total_chars))
            if (new_total_chars + len(field_values)) > 1024:
                #print("Reached threshold with new item. Adding current list len: {}".format(len(field_values)))
                # we'd go over, this goes in a new field
                data = ""
                for i in field_values:
                    data += "{}\n".format(i)
                embed.add_field(name=field_name, value=data, inline=inline)
                field_values = []
                total_chars = 0
            field_values.append(item)
            total_chars += len(item)
            #print("Appending item, total_chars: {}".format(total_chars))
        if len(field_values) > 0:
            data = ""
            for i in field_values:
                data += "{}\n".format(i)
            embed.add_field(name=field_name, value=data, inline=inline)


class Command(BaseCommand):
    help = "Runs the CLOT Bot"
    def handle(self, *args, **options):
        try:
            if settings.DEBUG:
                bot = WZBot()
                bot.run(os.environ['WZ_TEST_BOT_TOKEN'])
            else:
                bot = WZBot()
                bot.run(os.environ['WZ_BOT_TOKEN'])
        except SystemExit:
            pass
        except Exception:
            log_exception()
