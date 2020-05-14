import discord
from wlct.models import Clan, Player, DiscordUser, DiscordChannelClanFilter, DiscordChannelPlayerFilter, DiscordChannelTournamentLink, TournamentAdministrator
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournaments_by_division_id, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, get_team_data, ClanLeague, ClanLeagueTournament, ClanLeagueDivision, TournamentGame, TournamentGameEntry
from wlct.logging import ProcessGameLog, ProcessNewGamesLog, log_exception
from discord.ext import commands
from django.conf import settings
from wlct.cogs.common import is_clotadmin, has_tournament_admin_access


class PlayerStats:
    def __init__(self, wins, losses, tournaments, games, win_pct, rating):
        self.wins = wins
        self.losses = losses
        self.tournaments = tournaments
        self.games = games
        self.win_pct = win_pct
        self.rating = rating


class Clot(commands.Cog, name="clot"):
    def __init__(self, bot):
        self.bot = bot

    def get_player_stats(self, token):
        # return a tuple of all the player stats
        # this tuple will be (Success, Wins, Losses, Tournaments Played In, Games Played In, Win %)
        # first, grab the player
        if token == 0:
            return False, None
        player = Player.objects.filter(token=token)
        if player:
            player = player[0]
            wins = player.wins
            losses = player.losses
            rating = player.rating
            tpi = 0
            gpi = 0
            tplayer = TournamentPlayer.objects.filter(player=player)
            for p in tplayer:
                tpi += 1
                games = TournamentGameEntry.objects.filter(team=p.team)
                gpi += games.count()
            win_pct = 0
            if wins + losses != 0:
                win_pct = (wins / (wins + losses)) * 100
                win_pct = round(win_pct, 2)
            return True, PlayerStats(wins, losses, tpi, gpi, win_pct, rating)
        else:
            return False, None

    @commands.command(brief="View CLOT statistics",
                      usage='''
                          bb!stats clot - shows overall CLOT stats
                          bb!stats me - shows your personal stats
                          bb!stats token - shows the users CLOT stats based on Warzone token
                          bb!stats discord_name - shows the CLOT stats for a player matching that discord name
                      ''')
    async def stats(self, ctx, option=""):
        try:
            if option == "clot":
                emb = self.bot.get_default_embed()
                # grab total tournaments + games + players
                p = Player.objects.all()
                emb.add_field(name="# of Players", value="{}".format(p.count()))
                t = Tournament.objects.all()
                emb.add_field(name="# of Tournaments Created", value="{}".format(t.count()))
                g = TournamentGame.objects.all()
                emb.add_field(name="# of Games Played", value="{}".format(g.count()))
                await ctx.send(embed=emb)
            elif option == "me" or option.isnumeric() or option != "":
                token = 0
                discord_user = None
                if option == "me":
                    discord_user = ctx.message.author
                    discord_user_id = discord_user.id
                    player = Player.objects.filter(discord_member__memberid=discord_user_id)
                    if player:
                        token = player[0].token
                elif option.isnumeric():
                    # try to lookup the player by token
                    print("Option is numeric, using it as the token")
                    token = option
                else:
                    await ctx.send("bb!stats <player name> is currently under construction")
                    return
                    '''players = Player.objects.filter(name__istartswith=option)
                    message = await ctx.send("Searching all players I've seen for {}".format(option))
                    original_text = message.content
                    await self.bot.update_progress(message, original_text, 0.0)

                    users = self.bot.users
                    num_users = len(users)
                    step = 100.0 / num_users
                    current_step = step
                    for user in users:
                        user_name = user.name.lower()
                        if option in user_name:
                            discord_user = user
                            discord_user_id = discord_user.id
                            break
                        current_step += step
                        await self.bot.update_progress(message, original_text, round(current_step, 2))
                    await self.bot.update_progress(message, original_text, 100.0)'''


                stats = self.get_player_stats(token)
                if stats[0]:
                    # success
                    pstats = stats[1]
                    if discord_user:
                        emb = self.bot.get_embed(discord_user)
                    else:
                        emb = self.bot.get_default_embed()
                    emb.add_field(name="CLOT Rating", value="{}".format(pstats.rating))
                    emb.add_field(name="Overall Record", value="{}-{}".format(pstats.wins, pstats.losses))
                    emb.add_field(name="Winning %", value="{}".format(pstats.win_pct))
                    emb.add_field(name="Tournaments Played In", value="{}".format(pstats.tournaments))
                    emb.add_field(name="Games Played In", value="{}".format(pstats.games))
                    await ctx.send(embed=emb)
                else:
                    await ctx.send(self.bot.discord_link_text_user)
            else:
                await ctx.send("You must enter a valid option to the command. Use ``bb!help stats`` to see options.")
        except Exception as e:
            log_exception()

    @commands.command(brief="Admin commands to manage and debug CLOT",
                      usage='''
                          bb!admin logs -pg <gameid> - shows last 2 ProcessGame logs for game
                          bb!admin logs -png <tournamentid> - shows last 2 ProcessNewGame logs for tournament
                          bb!admin mtc -p - shows current players on the MTC
                          bb!admin mtc -r <player_token> - removes player from MTC using wz token
                          bb!admin rtl -p - shows current players on the RTL
                          bb!admin rtl -r <discord_id> - removes player from RTL using Discord ID
                          bb!admin cache <tournament_id> - forcibly runs the cache on a tournament
                          bb!admin add <player_token> <tournament_id> - adds this player as an admin for the tournament
                          ''',
                      category="clot")
    async def admin(self, ctx, cmd="", option="", arg=""):
        try:
            if cmd == "logs":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command.")
                    return
                if option == "-pg":
                    if arg:
                        game = TournamentGame.objects.filter(gameid=arg)
                        if game:
                            game_logs = ProcessGameLog.objects.filter(game=game[0]).order_by('-timestamp')[:2]
                            if game_logs:
                                await self.send_log_message(ctx, "process game", game_logs)
                            else:
                                await ctx.send("No process game logs were found with that game id")
                        else:
                            await ctx.send("Unable to find game with id: {}".format(arg))
                    else:
                        await ctx.send("Please enter a valid game id")
                elif option == "-png":
                    if arg and arg.isnumeric():
                        tournament = Tournament.objects.filter(id=int(arg))
                        if tournament:
                            new_game_logs = ProcessNewGamesLog.objects.filter(tournament=tournament[0]).order_by('-timestamp')[:2]
                            if new_game_logs:
                                await self.send_log_message(ctx, "process new game", new_game_logs)
                            else:
                                await ctx.send("No process new game logs were found with that tournament id")
                        else:
                            await ctx.send("Unable to find tournament with id: {}. Use ``bb!admin tournaments`` to see ids".format(arg))
                    else:
                        await ctx.send("Please enter a valid tournament id. Use the ``bb!tournaments`` command to see ids")
                elif option == "-tt":
                    if not is_clotadmin(ctx.message.author.id):
                        await ctx.send("Only CLOT admins can use this command.")
                        return
                    if arg and arg.isnumeric():
                        tt = TournamentTeam.objects.filter(id=int(arg))
                        if tt:
                            tt = tt[0]
                            players = TournamentPlayer.objects.filter(team=tt)
                            team_name_list = []
                            for player in players:
                                team_name_list.append(player.player.name)
                            team_str = ", ".join(team_name_list)
                            await ctx.send("Team {}\n{}\n{}".format(arg, team_str, tt.tournament.name))
                        else:
                            await ctx.send("Unable to find team with id: {}".format(arg))
                    else:
                        await ctx.send("Please enter a valid tournament team id")
                else:
                    await ctx.send("Please enter a valid option (-pg or -png)")
            elif cmd == "mtc":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only MTC admins can use this command.")
                    return
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
                    if arg:
                        try:
                            mtc.decline_tournament(arg)
                            await ctx.send("Successfully removed player from MTC with id: {}".format(arg))
                        except:
                            await ctx.send("Unable to remove player from MTC with id: {}".format(arg))
                    else:
                        ctx.send("Please enter a valid token. Use ``bb!admin mtc -p`` to see current players.")
                else:
                    await ctx.send("Please enter a valid option (-p or -r)")
            elif cmd == "rtl":
                rtl = RealTimeLadder.objects.filter(id=109)[0]
                if not has_tournament_admin_access(ctx.message.author.id, rtl):
                    await ctx.send("Only RTL admins can use this command.")
                    return
                if option == "-p":
                    tplayers = TournamentPlayer.objects.filter(tournament=rtl, team__active=True)
                    if tplayers:
                        player_data = "Current Players on the RTL:\n"
                        for tplayer in tplayers:
                            player_data += "{} | Discord Id: {}\n".format(tplayer.player.name, tplayer.player.discord_member.memberid)
                        await ctx.send(player_data)
                    else:
                        await ctx.send("Currently there are no players on the RTL")
                elif option == "-r":
                    if arg:
                        try:
                            rtl.leave_ladder(arg)
                            await ctx.send("Successfully removed player from RTL with id: {}".format(arg))
                        except:
                            await ctx.send("Unable to remove player from RTL with id: {}".format(arg))
                    else:
                        ctx.send("Please enter a valid id. Use ``bb!admin rtl -p`` to see current players.")
                else:
                    await ctx.send("Please enter a valid option (-p or -r)")
            elif cmd == "cache":
                # forcibly run the game caching
                if option.isnumeric():
                    # option is the tournament id to run caching on
                    tournament = find_tournament_by_id(int(option), True)
                    if not has_tournament_admin_access(ctx.message.author.id, tournament):
                        await ctx.send("Only tournament admins can use this command.")
                        return
                    if tournament:
                        self.bot.cache_queue.append(tournament.id)
                        await ctx.send("Successfully queued up {} to be re-cached".format(tournament.name))
                    else:
                        await ctx.send("Tournament {} does not exist.")
                else:
                    await ctx.send("Please enter a numeric id.")
            elif cmd == "process":
                if not option.isnumeric():
                    await ctx.send("Please enter a valid tournament id")
                    return
                tournament = find_tournament_by_id(int(option), True)
                if not has_tournament_admin_access(ctx.message.author.id, tournament):
                    await ctx.send("Only tournament admins can use this command.")
                    return
                if tournament:
                    self.bot.process_queue.append(tournament.id)
                    await ctx.send("Successfully queued up {} to be processed".format(tournament.name))
                    return
            elif cmd == "add":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command.")
                    return
                if option.isnumeric() and arg.isnumeric():
                    admin = TournamentAdministrator.objects.filter(player__token=option, tournament__id=int(arg))
                    if admin:
                        await ctx.send("{} is already an administrator of tournament {}".format(option, arg))
                        return
                    else:
                        player = Player.objects.filter(token=option)
                        if player:
                            tournament = find_tournament_by_id(int(arg), True)
                            if tournament:
                                admin = TournamentAdministrator(player=player[0], tournament=tournament)
                                admin.save()
                                await ctx.send("Added {} as a {} admin successfully.".format(player[0].name, tournament.name))
                                return
                await ctx.send("Please enter a valid player token and tournament id.")
            else:
                await ctx.send("Please enter a valid command. Use ``bb!help admin`` to see commands.")

        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(
        brief="Creates filters for game logs to only show games fulfilling criteria.",
        usage='''
                Hint: Any option with [] is optional. Excluding tournament_ids will apply filter to all games
                bb!filter -a -c clan_id [tournament_id] - adds filters for the channel to show logs from a clan
                bb!filter -r -c clan_id [tournament_id] - removes clan filters from the channel
                bb!filter -a -p player_token [tournament_id] - adds filters for the channel to show logs from a player
                bb!filter -r -p player_token [tournament_id] - removes player filters from the channel
                bb!filter -rall - removes all filters from the channel
                ''',
        category="clot")
    async def filter(self, ctx, arg="invalid_cmd", arg2="invalid_cmd", id="invalid_id", tournament_id=""):
        try:
            discord_user = DiscordUser.objects.filter(memberid=ctx.message.author.id)
            if not discord_user:
                discord_user = DiscordUser(memberid=ctx.message.author.id)
                discord_user.save()

            # Ensure parameters follow syntax
            if arg == "invalid_cmd" or arg != "-a" and arg != "-r" and arg != "-rall":
                await ctx.send("Please enter a valid option (-a or -r or -rall). Use ``bb!help filter`` to see commands.")
                return

            if arg != "-rall" and (arg2 == "invalid_cmd" or arg2 != "-c" and arg2 != "-p"):
                await ctx.send("Please enter a valid option (-c or -p). Use ``bb!help filter`` to see commands.")
                return

            if arg != "-rall" and (id == "invalid_id" or not id.isnumeric()):
                await ctx.send("Please enter a valid id. Use ``bb!help filter`` to see commands.")
                return

            if arg != "-rall" and tournament_id and not tournament_id.isnumeric():
                await ctx.send("Please enter a valid tournament ID (or exclude to filter all applicable games). Use ``bb!help tournaments`` to see tournaments.")
                return

            # we must find the tournament id, and the player associated with the discord user must be the creator
            # validate that here
            if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                # user is a server admin, process to create the channel -> tournament link
                if tournament_id:
                    tournament = find_tournament_by_id(int(tournament_id))
                    if not tournament:
                        await ctx.send("Unable to find tournament with id {}. Use ``bb!tournaments`` to see list of tournaments.".format(tournament_id))
                        return

                    discord_channel_link = DiscordChannelTournamentLink.objects.filter(channelid=ctx.message.channel.id,
                                                                                       tournament=tournament)
                else:
                    discord_channel_link = DiscordChannelTournamentLink.objects.filter(channelid=ctx.message.channel.id)

                if not discord_channel_link:
                    await ctx.send("There were no links found in this channel satisfying the command. Use ``bb!help linkt`` to see commands to link.")
                    return

                if arg2 == "-c":
                    clan = Clan.objects.filter(id=int(id))
                    if not clan:
                        await ctx.send(
                            "Unable to find clan with id {}. Use ``bb!clans`` to see list of clans.".format(id))
                        return
                    clan = clan[0]
                elif arg2 == "-p":
                    player = Player.objects.filter(token=id)
                    if not player:
                        await ctx.send("Unable to find player with token {}.".format(id))
                        return
                    player = player[0]

                if arg == "-a":
                    total_filters_added = 0
                    for cl in discord_channel_link:
                        if arg2 == "-c":
                            # Adds clan filters to the channel
                            discord_channel_filter = DiscordChannelClanFilter.objects.filter(link=cl, clan=clan)
                            if discord_channel_filter:
                                await ctx.send("Filter for {} and {} already exists. Use ``bb!links`` to see all links and filters.".format(clan.name, cl.tournament.name))
                                continue
                            new_filter = DiscordChannelClanFilter(link=cl, clan=clan)
                        else:
                            # Adds player filters to the channel
                            discord_channel_filter = DiscordChannelPlayerFilter.objects.filter(link=cl, player=player)
                            if discord_channel_filter:
                                await ctx.send("Filter for {} and {} already exists. Use ``bb!links`` to see all links and filters.".format(player.name, cl.tournament.name))
                                continue
                            new_filter = DiscordChannelPlayerFilter(link=cl, player=player)
                        new_filter.save()
                        total_filters_added += 1

                    await ctx.send("Successfully added {} filters to this channel.".format(total_filters_added))
                else:
                    total_filters_removed = 0
                    for cl in discord_channel_link:
                        if arg == "-rall":
                            # Remove all filters from the channel
                            clan_filters = DiscordChannelClanFilter.objects.filter(link=cl)
                            player_filters = DiscordChannelPlayerFilter.objects.filter(link=cl)
                            for cf in clan_filters:
                                cf.delete()
                                total_filters_removed += 1
                            for pf in player_filters:
                                pf.delete()
                                total_filters_removed += 1

                        elif arg2 == "-c":
                            # Remove all filters applying to the channel, clan and (optionally) tournament
                            discord_channel_filter = DiscordChannelClanFilter.objects.filter(link=cl, clan=clan)
                            if discord_channel_filter:
                                discord_channel_filter[0].delete()
                                total_filters_removed += 1

                        else:
                            # Remove all filters applying to the channel, player and (optionally) tournament
                            discord_channel_filter = DiscordChannelPlayerFilter.objects.filter(link=cl, player=player)
                            if discord_channel_filter:
                                discord_channel_filter[0].delete()
                                total_filters_removed += 1
                    if total_filters_removed:
                        await ctx.send("Successfully removed {} filters from the channel".format(total_filters_removed))
                    else:
                        await ctx.send("Unable to find any filters to remove. Use ``bb!links`` to see all links and filters.")
            else:
                await ctx.send("Sorry, you must be a server administrator to use this command.")
                return
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")


    '''
    Sends messages containing logs to the channel that the admin used to invoke the command.
    '''
    @staticmethod
    async def send_log_message(ctx, log_type, logs):
        if len(logs) == 1:
            ctx.send("One {} log found: [{} UTC]:\n{}".format(log_type, logs[0].timestamp, logs[0].msg[:1900]))
        else:
            await ctx.send("Last two {} logs: ".format(log_type))
            for log in logs:
                await ctx.send("[{} UTC]:\n{}".format(log.timestamp, log.msg[:1900]))

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
            if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                # user is a server admin, process to create the channel -> tournament link
                tournaments = find_tournaments_by_division_id(int(arg2))
                total_successfully_updated = 0
                total_filters_removed = 0
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
                            discord_channel_link = discord_channel_link[0]

                            clan_filters = DiscordChannelClanFilter.objects.filter(link=discord_channel_link)
                            for cf in clan_filters:
                                total_filters_removed += 1
                                cf.delete()
                            player_filters = DiscordChannelPlayerFilter.objects.filter(link=discord_channel_link)
                            for pf in player_filters:
                                total_filters_removed += 1
                                pf.delete()

                            discord_channel_link.delete()
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
                await ctx.send("You've removed the link to this channel for {} out of {} tournaments and {} filters.".format(
                    total_successfully_updated, len(tournaments), total_filters_removed))
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
            if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
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
                                if player.id != tournament.created_by.id and (tournament.id != 168) and (tournament.id != 109) and (tournament.id != 167) and (tournament.parent_tournament and tournament.parent_tournament.id != 51):  # hard code this for clan league
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
                        total_filters_removed = 0
                        discord_channel_link = DiscordChannelTournamentLink.objects.filter(tournament=tournament, channelid=ctx.message.channel.id)
                        if discord_channel_link:
                            discord_channel_link = discord_channel_link[0]
                            clan_filters = DiscordChannelClanFilter.objects.filter(link=discord_channel_link)
                            for cf in clan_filters:
                                total_filters_removed += 1
                                cf.delete()
                            player_filters = DiscordChannelPlayerFilter.objects.filter(link=discord_channel_link)
                            for pf in player_filters:
                                total_filters_removed += 1
                                pf.delete()

                            discord_channel_link.delete()
                            await ctx.send("You've removed the link from this channel and {} filters".format(total_filters_removed))
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
        brief="Shows all links and filters for the channel.",
        usage='''
            bb!links - List the links and filters for the channel
            ''',
        category="clot")
    async def links(self, ctx):
        try:
            discord_user = DiscordUser.objects.filter(memberid=ctx.message.author.id)
            if not discord_user:
                discord_user = DiscordUser(memberid=ctx.message.author.id)
                discord_user.save()

            # Get all of the channel links
            discord_channel_links = DiscordChannelTournamentLink.objects.filter(channelid=ctx.message.channel.id)
            if not discord_channel_links:
                await ctx.send("No links were found for this channel. Use ``bb!help linkt`` to see how to link.")
                return

            # List all channel links and create queryset of clan and player filters
            clan_filters = DiscordChannelClanFilter.objects.none()
            player_filters = DiscordChannelPlayerFilter.objects.none()
            message_data = "Tournament Links:\n"
            for cl in discord_channel_links:
                if len(message_data) > 1500:
                    await ctx.send(message_data)
                    message_data = ""

                message_data += "{} (ID: {})\n".format(cl.tournament.name, cl.tournament.id)

                clan_filters |= DiscordChannelClanFilter.objects.filter(link=cl)
                player_filters |= DiscordChannelPlayerFilter.objects.filter(link=cl)

            # List all clan filters
            message_data += "\nClan Filters:\n"
            for cf in clan_filters:
                if len(message_data) > 1500:
                    await ctx.send(message_data)
                    message_data = ""

                message_data += "{} (ID: {}) | {} (ID: {})\n".format(cf.clan.name, cf.clan.id, cf.link.tournament.name, cf.link.tournament.id)
            
            # List all player filters
            message_data += "\nPlayer Filters:\n"
            for pf in player_filters:
                if len(message_data) > 1500:
                    await ctx.send(message_data)
                    message_data = ""

                message_data += "{} (Token: {}) | {} (ID: {})\n".format(pf.player.name, pf.player.token, pf.link.tournament.name, pf.link.tournament.id)

            if message_data:
                await ctx.send(message_data)

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
            divisions = ClanLeagueDivision.objects.filter(league=cl).order_by('title')

            for division in divisions:
                if len(division_data) > 1500:
                    await ctx.send(division_data)
                    division_data = ""
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
                          bb!tournaments -s <search_text> : Searches for tournaments by their name
                          ''',
                          category="clot")
    async def tournaments(self, ctx, option="invalid", arg=""):
        try:
            tournament_data = ""
            tournaments = Tournament.objects.all()
            if option == "-f":
                tournament_data += "Finished Tournaments\n"
            elif option == "-o":
                tournament_data += "Open Tournaments\n"
            elif option == "-p":
                tournament_data += "Tournaments In Progress\n"
            elif option == "-cl":
                tournament_data += "Clan League Tournaments\n"
            elif option == "-s":
                await ctx.send("Searching for Tournaments starting with {}...".format(arg))
                tournaments = Tournament.objects.filter(name__istartswith=arg.lower(), private=False)[:10]
                data = "Showing top 10 results\n"
                for t in tournaments:
                    data += "{} (Id: {}) | <{}>\n".format(t.name, t.id, t.get_full_public_link())
                if data != "" and len(data) > 0:
                    await ctx.send(data)
                else:
                    await ctx.send("No tournaments found that start with {}".format(arg))
                return
            else:
                await ctx.send("You must specify an option. Use ``bb!help tournaments`` to see commands.")
                return

            await ctx.send("Gathering tournament data....")
            for tournament in tournaments:
                child_tournament = find_tournament_by_id(tournament.id, True)
                if child_tournament:
                    if len(tournament_data) > 1500:
                        await ctx.send(tournament_data)
                        tournament_data = ""

                    link_text = "http://wztourney.herokuapp.com/"
                    if child_tournament.is_league:
                        link_text += "leagues/{}".format(child_tournament.id)
                    else:
                        link_text += "tournaments/{}".format(child_tournament.id)
                    if option == "-f":  # only finished tournaments
                        if child_tournament.is_finished:
                            tournament_data += "{} (Id: {}) | <{}> | Winner: {}\n".format(child_tournament.name, child_tournament.id, link_text,
                                                                         get_team_data(child_tournament.winning_team))
                    elif option == "-o":  # only open tournaments
                        if not child_tournament.has_started and not child_tournament.private:
                            tournament_data += "{} (Id: {}) | <{}> | {}\n".format(child_tournament.name, child_tournament.id, link_text,
                                                                               child_tournament.spots_left)
                    elif option == "-p":  # only in progress
                        if child_tournament.has_started and not child_tournament.private:
                            tournament_data += "{} (Id: {}) | <{}>\n".format(child_tournament.name, child_tournament.id, link_text)
                    elif option == "-cl":  # only in progress
                        if child_tournament.id == 51 and child_tournament.has_started:
                            cl_tourneys = ClanLeagueTournament.objects.filter(parent_tournament=child_tournament).order_by('id')
                            for cl_tourney in cl_tourneys:
                                tournament_data += "{} (Id: {})\n".format(cl_tourney.name, cl_tourney.id)
            if len(tournament_data) > 0:
                await ctx.send(tournament_data)
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(brief="Displays the MTC top ten on the CLOT. Optional arguments to show any MTC top 10.",
                      usage="""
                      Hint: official MTC will be selected if no id is included
                      bb!mtc <league_id>
                      """)
    async def mtc(self, ctx, mtc_id="0"):
        try:
            tournament_data = ""

            if mtc_id == "0":
                mtc_id = "22"

            if not mtc_id.isnumeric():
                await ctx.send("You've entered and invalid MTC league id.")
                return

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
    async def clan(self, ctx, clanid="", discord_arg=""):
        try:
            if not clanid:
                await ctx.send("No clanid has been entered. Please use ``bb!clans`` to show clans.")
                return
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
                    if len(player_data) > 0:
                        emb.add_field(name=field_name, value=player_data)
                    await ctx.send(embed=emb)
                else:
                    await ctx.send("No players are registered on the CLOT for {}".format(clan_obj[0].name))
            else:
                await ctx.send("Clan with id {} not found. Please use bb!clans to show valid clans.".format(clanid))
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(brief="Displays all clans on the CLOT")
    async def clans(self, ctx):
        try:
            clans = Clan.objects.all().order_by('id')
            await ctx.send("Gathering clans data....")
            clans_data = "Clans on the CLOT\n\n"
            for clan in clans:
                player = Player.objects.filter(clan=clan)
                if player:
                    if len(clans_data) > 1500:
                        await ctx.send(clans_data)
                        clans_data = ""
                    clans_data += "{}: {}\n".format(clan.id, clan.name)
            await ctx.send(clans_data)
        except:
            log_exception()
            ctx.send("An error has occurred, unable to process command.")

    @commands.command(brief="Display your Warzone Profile Link and Searches for others",
                      usage='''
                          bb!profile - Displays your personal warzone profile
                          bb!profile master - Displays warzone profile for players starting with 'master' 
                      ''')
    async def profile(self, ctx, option=""):
        try:
            if option == "":
                discord_id = ctx.message.author.id
                player = Player.objects.filter(discord_member__memberid=discord_id)
                if player:
                    player = player[0]
                    await ctx.send("{} | <http://wzclot.com/stats/{}> | <https://warzone.com/Profile?p={}>".format(player.name, player.token, player.token))
                else:
                    await ctx.send("Your discord account is not linked to the CLOT. Please see http://wztourney.herokuapp.com/me/ for instructions.")
            else:
                await ctx.send("Searching the CLOT for players starting with {}...".format(option))
                players = Player.objects.filter(name__istartswith=option)
                data = ""
                current_player = 0
                for player in players:
                    current_player += 1
                    data += "{} | {} | <http://wzclot.com/stats/{}> | <https://warzone.com/Profile?p={}>\n".format(player.name, player.token, player.token, player.token)
                    if current_player % 20 == 0:
                        if data != "" and len(data) > 0:
                            await ctx.send(data)
                            data = ""
                if data != "" and len(data) > 0:
                    await ctx.send(data)
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")


def setup(bot):
    bot.add_cog(Clot(bot))