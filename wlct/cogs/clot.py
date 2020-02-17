import discord
from wlct.models import Clan, Player, DiscordUser
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, get_team_data
from discord.ext import commands
from django.conf import settings


class Clot(commands.Cog, name="clot"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        brief="Links your discord account with your CLOT/Warzone account for use with creating games and bot ladders.",
        usage="bot_token_from_clot_site",
        category="clot")
    async def linkme(self, ctx, arg):
        if isinstance(ctx.message.channel, discord.DMChannel):
            print("Token for linking: {} for user: {}".format(arg, ctx.message.author.id))
            # check to see if this player is already linked
            player = Player.objects.filter(bot_token=arg)
            if player:
                player = player[0]
                if player.discord.memberid == ctx.message.author.id:
                    await ctx.send("You're account is already linked on the CLOT.")
                elif player.discord is None:
                    print("Saving discord id: {} for user".format(ctx.message.author.id))
                    discord_obj = DiscordUser(memberid=ctx.message.author.id)
                    discord_obj.save()
                    player.discord = discord_obj
                    player.save()
                    await ctx.send("You've successfully linked your discord account to the CLOT.")
            else:
                await ctx.send(
                    "Bot token is invalid. Please visit http://wztourney.herokuapp.com/me to retrieve your token.")
        else:
            await ctx.send("You cannot use the !linkme command unless you are privately messaging the bot.")

    @commands.command(brief="Displays tournament data from the CLOT",
                      usage='''
                      bb!tournaments -f : Displays Finished Tournaments
                      bb!tournaments -o : Displays Open Tournaments
                      ''')
    async def tournaments(self, ctx, arg):
        await ctx.send("Gathering tournament data....")
        tournament_data = ""
        tournaments = Tournament.objects.all()
        if arg == "-f":
            tournament_data += "Finished Tournaments\n"
        elif arg == "-o":
            tournament_data += "Open Tournaments\n"
        else:
            await ctx.send("You must specify an option.")

        for tournament in tournaments:
            child_tournament = find_tournament_by_id(tournament.id, True)
            if child_tournament:
                if arg == "-f":  # only finished tournaments
                    if child_tournament[0].is_finished:
                        tournament_data += "{}, Winner: {}\n".format(child_tournament[0].name,
                                                                     get_team_data(child_tournament[0].winning_team))
                elif arg == "-o":  # only open tournaments
                    if not child_tournament[0].has_started and not child_tournament[0].private:
                        tournament_data += "{} has {} spots left\n".format(child_tournament[0].name,
                                                                           child_tournament[0].spots_left)
        await ctx.send(tournament_data)

    @commands.command(brief="Displays the MTC top ten on the CLOT")
    async def mtc(self, ctx):
        await ctx.send("Gathering Monthly Template Rotation data....")
        tournament_data = ""
        tournament = MonthlyTemplateRotation.objects.filter(id=22)
        if tournament:
            tournament = tournament[0]
            tournamentteams = TournamentTeam.objects.filter(tournament=tournament.id, active=True).order_by('-rating',
                                                                                                            '-wins')
            tournament_data += "MTC Top 10\n"
            teams_found = 0
            for team in tournamentteams:
                if teams_found <= 10:
                    games_finished = get_games_finished_for_team_since(team.id, tournament, 90)
                    if games_finished >= 10:
                        tournament_data += "{}) {} - {}\n".format(teams_found + 1, get_team_data_no_clan(team), team.rating)
                        teams_found += 1

        print("MTC: {}\nLength: {}".format(tournament_data, len(tournament_data)))
        await ctx.send(tournament_data)

    @commands.command(brief="Displays all registered clan members on the CLOT",
                      usage='''
                      Hint: to see a list of clan ids, use bb!clans
                      bb!clan clanid
                      ''')
    async def clan(self, ctx, clanid):
        await ctx.send("Gathering player data for clan {}....".format(clanid))
        clan_obj = Clan.objects.filter(pk=int(clanid))
        emb = discord.Embed(color=self.bot.embed_color)
        if clan_obj:
            emb.title = "{}".format(clan_obj[0].name)
            emb.set_thumbnail(url=clan_obj[0].image_path)
            player_data = ""
            players = Player.objects.filter(clan=clan_obj[0].id).order_by('name')
            current_player = 0
            if players:
                for player in players:
                    current_player += 1
                    player_data += "{} [Profile](https://www.warzone.com/Profile?p={})\n".format(player.name, player.token)
                    if current_player % 10 == 0:
                        emb.add_field(name="Registered on CLOT", value=player_data)
                        player_data = ""  # reset this for the next embed
                emb.add_field(name="Registered members on CLOT", value=player_data)
                await ctx.send(embed=emb)
            else:
                await ctx.send("No players are registered on the CLOt for {}".format(clan_obj[0].name))
        else:
            await ctx.send("Clan with id {} not found. Please use bb!clans to show valid clans.".format(clanid))

    @commands.command(brief="Display your Warzone Profile Link")
    async def profile(self, ctx):
        discord_id = ctx.message.author.id

        player = Player.objects.filter(discord__memberid=discord_id)
        if player:
            await ctx.send("{} | https://warzone.com/Profile?p={}".format(player.name, player.token))
        else:
            await ctx.send("Your discord account is not linked to the CLOT. Please see http://wztourney.herokuapp.com/me/ for instructions.")

    @commands.command(brief="Displays all clans on the CLOT")
    async def clans(self, ctx):
        clans = Clan.objects.all()
        await ctx.send("Gathering clans data....")
        clans_data = "Clans on the CLOT\n\n"
        for clan in clans:
            player = Player.objects.filter(clan=clan)
            if player:
                clans_data += "{}: {}\n".format(clan.id, clan.name)
        await ctx.send(clans_data)

def setup(bot):
    bot.add_cog(Clot(bot))