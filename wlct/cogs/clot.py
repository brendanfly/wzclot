import discord
from wlct.models import Clan, Player, DiscordUser, DiscordChannelTournamentLink
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournaments_by_division_id, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, get_team_data, ClanLeague, ClanLeagueTournament, ClanLeagueDivision
from wlct.logging import log_exception
from discord.ext import commands
from django.conf import settings
from wlct.cogs.common import has_admin_access, is_admin

class Clot(commands.Cog, name="clot"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(brief="Admin commands to manage and debug CLOT",
                      usage='''
                          bb!admin logs - shows logs
                          bb!admin mtc -p - shows current players on the MTC
                          bb!admin mtc -r <player_token> - removes player from MTC using wz token
                          bb!admin rtl -p - shows current players on the RTL
                          bb!admin rtl -r <discord_id> - removes player from RTL using Discord ID
                          ''',
                      category="clot")
    async def admin(self, ctx, cmd="", option="", token=""):
        try:
            if  has_admin_access(ctx.message.author.id):
                if cmd == "logs":
                    pass
                elif cmd == "mtc":
                    mtc = MonthlyTemplateRotation.objects.filter(id=22)[0]
                    if option == "-p":
                        tplayers = TournamentPlayer.objects.filter(tournament=mtc)
                        if tplayers:
                            player_data = "Current Players on the MTC:\n"
                            for tplayer in tplayers:
                                if tplayer.team.active:
                                    player_data += "{} | Id: {}\n".format(tplayer.player.name,
                                                                                  tplayer.player.token)
                            await ctx.send(player_data)
                        else:
                            await ctx.send("Currently there are no players on the MTC")
                    elif option == "-r":
                        if token:
                            try:
                                mtc.decline_tournament(token)
                                await ctx.send("Successfully removed player from MTC with id: {}".format(token))
                            except:
                                await ctx.send("Unable to remove player from MTC with id: {}".format(token))
                        else:
                            ctx.send("Please enter a valid token. Use ``bb!admin mtc -p`` to see current players.")
                    else:
                        await ctx.send("Please enter a valid option (-p or -r)")
                elif cmd == "rtl":
                    rtl = RealTimeLadder.objects.filter(id=109)[0]
                    if option == "-p":
                        tplayers = TournamentPlayer.objects.filter(tournament=rtl)
                        if tplayers:
                            player_data = "Current Players on the RTL:\n"
                            for tplayer in tplayers:
                                if tplayer.team.active:
                                    player_data += "{} | Discord Id: {}\n".format(tplayer.player.name, tplayer.player.discord_member.memberid)
                            await ctx.send(player_data)
                        else:
                            await ctx.send("Currently there are no players on the RTL")
                    elif option == "-r":
                        if token:
                            try:
                                rtl.leave_ladder(token)
                                await ctx.send("Successfully removed player from RTL with id: {}".format(token))
                            except:
                                await ctx.send("Unable to remove player from RTL with id: {}".format(token))
                        else:
                            ctx.send("Please enter a valid id. Use ``bb!admin rtl -p`` to see current players.")
                    else:
                        await ctx.send("Please enter a valid option (-p or -r)")
                else:
                    await ctx.send("Please enter a valid command. Use ``bb!help admin`` to see commands.")
            else:
                await ctx.send("Only clot-admin's can use this command.")
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(
        brief="Links a channel on your server to CL division tournaments on the CLOT. You must be the tournament creator to succesfully link the tournament.",
        usage='''
            bb!linkd -a division_id - adds a link from this discord channel to stream game logs for tournaments from division_id
            bb!linkd -r division_id - removes an existing link from this discord channel for tournaments from division_id
            ''',
        category="clot")
    async def linkd(self, ctx, arg="invalid_cmd", arg2="invalid_id"):
        try:
            discord_user = DiscordUser.objects.filter(memberid=ctx.message.author.id)
            if not discord_user:
                discord_user = DiscordUser(memberid=ctx.message.author.id)
                discord_user.save()
            else:
                discord_user = discord_user[0]

            if arg == "invalid_cmd":
                # list the current links for this channel
                links = "__**Tournaments Linked to this Channel**__\n"
                discord_channel_link = DiscordChannelTournamentLink.objects.filter(channelid=ctx.message.channel.id)
                if discord_channel_link.count() == 0:
                    links += "There are currently no links."
                else:
                    for link in discord_channel_link:
                        links += link.tournament.name + "\n"
                await ctx.send(links)
                return
            elif arg != "-a" and arg != "-r":
                await ctx.send("Please enter a valid option for the command (-a or -r).")
                return

            if arg2 == "invalid_id" or not arg2.isnumeric():
                await ctx.send("Please enter a valid division id to link to this channel.")
                return

            # we must find the tournament id, and the player associated with the discord user must be the creator
            # validate that here
            if ctx.message.author.guild_permissions.administrator or is_admin(ctx.message.author.id):
                # user is a server admin, process to create the channel -> tournament link
                tournaments = find_tournaments_by_division_id(int(arg2))
                total_successfully_updated = 0
                if not tournaments:
                    await ctx.send(
                        "Please enter a valid division id to link to this channel. Use ``bb!divisions`` to see list of divisions.")
                    return
                for tournament in tournaments:
                    # if a private tournament, the person sending this command must be linked and be the creator
                    if tournament.private:
                        player = Player.objects.filter(discord_member__memberid=ctx.message.author.id)
                        if player:
                            player = player[0]
                            if hasattr(tournament, 'parent_tournament'):
                                if tournament.parent_tournament:
                                    print("Tournament Parent ID {}".format(tournament.parent_tournament.id))
                                if player.id != tournament.created_by.id and (
                                        tournament.parent_tournament and tournament.parent_tournament.id != 51):  # hard code this for clan league
                                    await ctx.send(
                                        "The creator of the tournament is the only one who can link private tournaments: {}".format(
                                            tournament.name))
                                    continue
                            else:
                                # no parent tournament, must be creator
                                if player.id != tournament.created_by.id:
                                    await ctx.send(
                                        "The creator of the tournament is the only one who can link private tournaments: {}".format(
                                            tournament.name))
                                    continue
                        else:
                            await ctx.send(
                                "Your discord account is not linked to the CLOT. Please see http://wztourney.herokuapp.com/me/ for instructions.")
                            return
                    if arg == "-a":
                        # there can be a many:1 relationship from tournaments to channel, so it's completely ok if there's
                        # already a tournament hooked up to this channel. We don't even check, just add this tournament
                        # as a link to this channel
                        discord_channel_link = DiscordChannelTournamentLink.objects.filter(tournament=tournament,
                                                                                           channelid=ctx.message.channel.id)
                        if discord_channel_link:
                            await ctx.send("You've already linked this channel to tournament: {}".format(tournament.name))
                            continue
                        discord_channel_link = DiscordChannelTournamentLink(tournament=tournament,
                                                                            discord_user=discord_user,
                                                                            channelid=ctx.message.channel.id)
                        discord_channel_link.save()
                        total_successfully_updated += 1
                    elif arg == "-r":
                        discord_channel_link = DiscordChannelTournamentLink.objects.filter(tournament=tournament,
                                                                                           channelid=ctx.message.channel.id)
                        if discord_channel_link:
                            discord_channel_link[0].delete()
                            total_successfully_updated += 1
                        else:
                            await ctx.send(
                                "There is no existing link for tournament {} and this channel.".format(tournament.name))
            else:
                await ctx.send("Sorry, you must be a server administrator to use this command.")
            if total_successfully_updated and arg == "-a":
                await ctx.send(
                    "You've linked this channel to {} out of {} tournaments. Game logs will now show-up here in real-time.".format(
                        total_successfully_updated, len(tournaments)))
            elif total_successfully_updated and arg == "-r":
                await ctx.send("You've removed the link to this channel for {} out of {} tournaments.".format(
                    total_successfully_updated, len(tournaments)))
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(
        brief="Links a channel on your server to a tournament on the CLOT. You must be the tournament creator to succesfully link the tournament.",
        usage='''
            Hint: you can link the RTL (id: 109) and the MTC (id: 22) game logs
            bb!linkt -a tournament_id - adds a link from this discord channel to stream game logs for tournament_id
            bb!linkt -r tournament_id - removes an existing link from this discord channel to tournament_id
            ''',
        category="clot")
    async def linkt(self, ctx, arg="invalid_cmd", arg2="invalid_id"):
        try:
            discord_user = DiscordUser.objects.filter(memberid=ctx.message.author.id)
            if not discord_user:
                discord_user = DiscordUser(memberid=ctx.message.author.id)
                discord_user.save()
            else:
                discord_user = discord_user[0]

            if arg == "invalid_cmd":
                # list the current links for this channel
                links = "__**Tournaments Linked to this Channel**__\n"
                discord_channel_link = DiscordChannelTournamentLink.objects.filter(channelid=ctx.message.channel.id)
                if discord_channel_link.count() == 0:
                    links += "There are currently no links."
                else:
                    for link in discord_channel_link:
                        links += link.tournament.name + "\n"
                await ctx.send(links)
                return
            elif arg != "-a" and arg != "-r":
                await ctx.send("Please enter a valid option for the command (-a or -r).")
                return

            if arg2 == "invalid_id" or not arg2.isnumeric():
                await ctx.send("Please enter a valid tournament or league id to link to this channel.")
                return

            # we must find the tournament id, and the player associated with the discord user must be the creator
            # validate that here
            if ctx.message.author.guild_permissions.administrator or is_admin(ctx.message.author.id):
                # user is a server admin, process to create the channel -> tournament link
                tournament = find_tournament_by_id(int(arg2), True)
                if tournament:
                    # if a private tournament, the person sending this command must be linked and be the creator
                    if tournament.private:
                        player = Player.objects.filter(discord_member__memberid=ctx.message.author.id)
                        if player:
                            player = player[0]
                            if hasattr(tournament, 'parent_tournament'):
                                if tournament.parent_tournament:
                                    print("Tournament Parent ID {}".format(tournament.parent_tournament.id))
                                if player.id != tournament.created_by.id and (tournament.parent_tournament and tournament.parent_tournament.id != 51):  # hard code this for clan league
                                    await ctx.send("The creator of the tournament is the only one who can link private tournaments.")
                                    return
                            else:
                                # no parent tournament, must be creator
                                if player.id != tournament.created_by.id:
                                    await ctx.send(
                                        "The creator of the tournament is the only one who can link private tournaments.")
                                    return
                        else:
                            await ctx.send("Your discord account is not linked to the CLOT. Please see http://wztourney.herokuapp.com/me/ for instructions.")
                            return
                    if arg == "-a":
                        # there can be a many:1 relationship from tournaments to channel, so it's completely ok if there's
                        # already a tournament hooked up to this channel. We don't even check, just add this tournament
                        # as a link to this channel
                        discord_channel_link = DiscordChannelTournamentLink.objects.filter(tournament=tournament, channelid=ctx.message.channel.id)
                        if discord_channel_link:
                            await ctx.send("You've already linked this channel to tournament: {}".format(tournament.name))
                            return
                        discord_channel_link = DiscordChannelTournamentLink(tournament=tournament, discord_user=discord_user, channelid=ctx.message.channel.id)
                        discord_channel_link.save()
                        await ctx.send("You've linked this channel to tournament: {}. Game logs will now show-up here in real-time.".format(tournament.name))
                    elif arg == "-r":
                        discord_channel_link = DiscordChannelTournamentLink.objects.filter(tournament=tournament, channelid=ctx.message.channel.id)
                        if discord_channel_link:
                            discord_channel_link[0].delete()
                            await ctx.send("You've removed the link from this channel and tournament: {}".format(tournament.name))
                        else:
                            await ctx.send("There is no existing link for tournament {} and this channel.")
                else:
                    await ctx.send("Please enter a valid tournament or league id to link to this channel.")
            else:
                await ctx.send("Sorry, you must be a server administrator to use this command.")
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(
        brief="Links your discord account with your CLOT/Warzone account for use with creating games and bot ladders.",
        usage="bot_token_from_clot_site",
        category="clot")
    async def linkme(self, ctx, arg):
        try:
            if isinstance(ctx.message.channel, discord.DMChannel):
                print("Token for linking: {} for user: {}".format(arg, ctx.message.author.id))
                # check to see if this player is already linked
                player = Player.objects.filter(bot_token=arg)
                if player:
                    player = player[0]
                    # make sure the discord id is not already here
                    current_discord = Player.objects.filter(discord_member__memberid=ctx.message.author.id)
                    if current_discord:
                        current_discord = current_discord[0]
                        cd_name = self.bot.get_user(current_discord.discord_member.memberid)
                        new_name = ctx.message.author.name

                        # do the unlinking
                        player.discord_member = None
                        player.save()
                        await ctx.send("Your discord ID is already associated with another account, unlinking {} and linking {}.".format(cd_name, new_name))

                    if player.discord_member is not None and player.discord_member.memberid == ctx.message.author.id:
                        await ctx.send("You're account is already linked on the CLOT.")
                    elif player.discord_member is None:
                        print("Saving discord id: {} for user".format(ctx.message.author.id))
                        discord_obj = DiscordUser.objects.filter(memberid=ctx.message.author.id)
                        if not discord_obj:
                            discord_obj = DiscordUser(memberid=ctx.message.author.id)
                            discord_obj.save()
                        else:
                            discord_obj = discord_obj[0]
                        player.discord_member = discord_obj
                        player.save()
                        await ctx.send("You've successfully linked your discord account to the CLOT.")
                else:
                    await ctx.send(
                        "Bot token is invalid. Please visit http://wztourney.herokuapp.com/me to retrieve your token.")
            else:
                await ctx.send("You cannot use the !linkme command unless you are privately messaging the bot.")
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(brief="Displays division data from the CLOT",
                      usage='''
                          bb!divisions : Displays CL Divisions
                          ''',
                      category="clot")
    async def divisions(self, ctx):
        try:
            await ctx.send("Gathering tournament data....")
            division_data = "Clan League Divisions\n"

            cl = ClanLeague.objects.filter(id=51)[0]
            divisions = ClanLeagueDivision.objects.filter(league=cl).order_by('+title')

            for division in divisions:
                division_data += "{} | Id: {}\n".format(division.title, division.id)

            await ctx.send(division_data)
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(brief="Displays tournament data from the CLOT",
                      usage='''
                          bb!tournaments -f : Displays Finished Tournaments
                          bb!tournaments -o : Displays Open Tournaments
                          bb!tournaments -p : Displays Tournaments In Progress
                          bb!tournaments -cl : Displays Clan League Tournaments
                          ''',
                          category="clot")
    async def tournaments(self, ctx, arg):
        try:
            await ctx.send("Gathering tournament data....")
            tournament_data = ""
            tournaments = Tournament.objects.all()
            if arg == "-f":
                tournament_data += "Finished Tournaments\n"
            elif arg == "-o":
                tournament_data += "Open Tournaments\n"
            elif arg == "-p":
                tournament_data += "Tournaments In Progress\n"
            elif arg == "-cl":
                tournament_data += "Clan League Tournaments\n"
            else:
                await ctx.send("You must specify an option. Use ``bb!help tournaments`` to see commands.")

            for tournament in tournaments:
                child_tournament = find_tournament_by_id(tournament.id, True)
                if child_tournament:
                    link_text = "http://wztourney.herokuapp.com/"
                    if child_tournament.is_league:
                        link_text += "leagues/{}".format(child_tournament.id)
                    else:
                        link_text += "tournaments/{}".format(child_tournament.id)
                    if arg == "-f":  # only finished tournaments
                        if child_tournament.is_finished:
                            tournament_data += "{} | <{}> | Winner: {}\n".format(child_tournament.name, link_text,
                                                                         get_team_data(child_tournament.winning_team))
                    elif arg == "-o":  # only open tournaments
                        if not child_tournament.has_started and not child_tournament.private:
                            tournament_data += "{} | <{}> | {} spots left\n".format(child_tournament.name, link_text,
                                                                               child_tournament.spots_left)
                    elif arg == "-p":  # only in progress
                        if child_tournament.has_started and not child_tournament.private:
                            tournament_data += "{} | <{}>\n".format(child_tournament.name, link_text)
                    elif arg == "-cl":  # only in progress
                        if child_tournament.id == 51 and child_tournament.has_started:
                            cl_tourneys = ClanLeagueTournament.objects.filter(parent_tournament=child_tournament).order_by('id')
                            for cl_tourney in cl_tourneys:
                                tournament_data += "{} | Id: {}\n".format(cl_tourney.name, cl_tourney.id)
            await ctx.send(tournament_data)
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(brief="Displays the MTC top ten on the CLOT. Optional arguments to show any MTC top 10.",
                      usage='bb!mtc <league_id>')
    async def mtc(self, ctx, mtc_id="0"):
        try:
            tournament_data = ""

            if mtc_id == "0":
                mtc_id = "22"

            tournament = MonthlyTemplateRotation.objects.filter(id=int(mtc_id))
            if tournament:
                await ctx.send("Gathering Monthly Template Rotation data....")
                tournament = tournament[0]
                tournamentteams = TournamentTeam.objects.filter(tournament=tournament.id, active=True).order_by('-rating',
                                                                                                                '-wins')
                tournament_data += "MTC Top 10\n"
                teams_found = 0
                for team in tournamentteams:
                    if teams_found < 10:
                        games_finished = get_games_finished_for_team_since(team.id, tournament, 90)
                        if games_finished >= 10:
                            tournament_data += "{}) {} - {}\n".format(teams_found + 1, get_team_data_no_clan(team), team.rating)
                            teams_found += 1
                print("MTC: {}\nLength: {}".format(tournament_data, len(tournament_data)))
                await ctx.send(tournament_data)
            else:
                await ctx.send("You've entered an invalid MTC league id.")
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(brief="Displays all registered clan members on the CLOT",
                      usage='''
                          Hint: to see a list of clan ids, use bb!clans
                          bb!clan clanid
                          bb!clan clanid -d - List of players in the clan who have linked their discord accounts
                          ''')
    async def clan(self, ctx, clanid, discord_arg=""):
        try:
            await ctx.send("Gathering player data for clan {}....".format(clanid))
            clan_obj = Clan.objects.filter(pk=int(clanid))
            emb = discord.Embed(color=self.bot.embed_color)
            if clan_obj:
                emb.title = "{}".format(clan_obj[0].name)
                emb.set_thumbnail(url=clan_obj[0].image_path)
                player_data = ""
                field_name = ""
                if discord_arg != "-d":
                    field_name = "Registered on CLOT"
                    players = Player.objects.filter(clan=clan_obj[0].id).order_by('name')
                else:
                    field_name = "Discord Linked on CLOT"
                    players = Player.objects.filter(clan=clan_obj[0].id, discord_member__isnull=False).order_by('name')
                current_player = 0
                if players:
                    for player in players:
                        current_player += 1
                        player_data += "{} [Profile](https://www.warzone.com/Profile?p={})\n".format(player.name, player.token)
                        if current_player % 10 == 0:
                            emb.add_field(name=field_name, value=player_data)
                            player_data = ""  # reset this for the next embed
                    emb.add_field(name=field_name, value=player_data)
                    await ctx.send(embed=emb)
                else:
                    await ctx.send("No players are registered on the CLOt for {}".format(clan_obj[0].name))
            else:
                await ctx.send("Clan with id {} not found. Please use bb!clans to show valid clans.".format(clanid))
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(brief="Displays all clans on the CLOT")
    async def clans(self, ctx):
        try:
            clans = Clan.objects.all()
            await ctx.send("Gathering clans data....")
            clans_data = "Clans on the CLOT\n\n"
            for clan in clans:
                player = Player.objects.filter(clan=clan)
                if player:
                    clans_data += "{}: {}\n".format(clan.id, clan.name)
            await ctx.send(clans_data)
        except:
            log_exception()
            ctx.send("An error has occurred, unable to process command.")

    @commands.command(brief="Display your Warzone Profile Link")
    async def profile(self, ctx):
        try:
            discord_id = ctx.message.author.id

            player = Player.objects.filter(discord_member__memberid=discord_id)
            if player:
                await ctx.send("{} | https://warzone.com/Profile?p={}".format(player.name, player.token))
            else:
                await ctx.send("Your discord account is not linked to the CLOT. Please see http://wztourney.herokuapp.com/me/ for instructions.")
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")


def setup(bot):
    bot.add_cog(Clot(bot))