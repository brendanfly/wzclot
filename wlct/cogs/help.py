import discord

from discord.ext import commands

def setup(bot):
    bot.help_command = Help()


def get_help_embed(cog):
    # start by building an embed for the help
    owner = cog.context.bot.owner
    emb = discord.Embed(color=cog.context.bot.embed_color)
    emb.description = "Made by {}.".format(owner)
    emb.set_thumbnail(
        url="http://www.tntmagazine.com/media/content/_master/57384/images/my_car_check_help_button1.jpg?size=1024")
    emb.set_author(icon_url=cog.context.author.avatar_url, name=cog.context.author)
    emb.title = "-B's Warzone Bot Help"
    emb.description = "Command prefix: bb!\nFor command usage type 'bb!help command'."
    emb.set_footer(text="Bot created and maintained by -B#0292")

    for cog in cog.context.bot.cogs.values():
        cmds = ""
        for command in cog.get_commands():
            cmds += "*{}*\n".format(command.name)
        if len(cmds) > 0:
            emb.add_field(name="__**{} commands**__".format(cog.qualified_name), value="{}".format(cmds), inline=True)

    emb.add_field(name="Useful Links:", value="[CLOT Website](http://wzclot.eastus.cloudapp.azure.com)", inline=False)
    return emb

class Help(commands.HelpCommand):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.verify_checks = False

    def command_not_found(self, string):
        return 'No command called "{}" found.'.format(string)

    def get_command_signature(self, command):
        return f"[{command.cog.qualified_name.upper()}] > {command.qualified_name}"

    async def send_bot_help(self, mapping):
        emb = get_help_embed(self)
        await self.context.send(embed=emb)

    async def send_cog_help(self, cog):
        pass

    async def send_command_help(self, command):
        # build the help string for the command
        emb = discord.Embed(color=self.context.bot.embed_color)
        emb.title = "{}".format(command.name)
        emb.description = "{}".format(command.brief)
        if command.usage is not None:
            emb.add_field(name="Examples:", value="{}".format(command.usage))
        await self.context.send(embed=emb)
