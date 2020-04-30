from django.db import models
from django.utils import timezone
from wlct.models import Player
from django.contrib import admin
from wlct.logging import log_cb_msg, log_exception

def get_team_data_no_clan_player_list(list):
    team_data = ""
    for player_token in list:
        players = Player.objects.filter(token=player_token)
        for player in players:
            team_data += '{} '.format(player.name)
    return team_data

# Models for the Off-site betting for the CLOT
def get_clotbook():
    cb = CLOTBook.objects.all()
    if cb.count() == 1:
        return cb[0]
    else:
        cb = CLOTBook()
        cb.save()
        return cb


class DecimalOddsAdjustment:

    def __init_(self, odds_num, odds_value, adjustment_direction):
        self.odds_num = odds_num
        self.odds_value = odds_value
        self.adjustment_direction = adjustment_direction

    def adjust(self):
        self.odds_value += self.adjustment_direction
        return self.odds_value

class CLOTBook(models.Model):
    total_bets = models.BigIntegerField(default=0)
    in_progress_bets = models.BigIntegerField(default=0)

    currency_name = "Coins"

    # always gives the probability to win for ratings1 based on the opponents of ratings2
    def probability_to_win(self, ratings1, ratings2):
        prob_win = round((1 / (10**((-(ratings1-ratings2))/400) + 1)), 2)
        log_cb_msg("Probability: Favorite: {}/{}, Underdog {}/{}".format(ratings1, prob_win, ratings2, 1-prob_win))
        return (prob_win, 1-prob_win)

    def calculate_decimal_odds_winnings(self, odds, wager):
        # winnings are calculated based on the wager and the current odds
        # ex. odds of -105 means you'd have to bet 100 to win 105
        return (wager*odds)-wager

    def calculate_american_odds_winnings(self, odds, wager):
        odds = self.american_odds_to_decimal(odds)
        return self.calculate_decimal_odds_winnings(odds, wager)

    def decimal_odds_to_american(self, odds):
        if odds > 2.0:
            return int((odds-1)*100)
        else:
            return int(-100 // (odds-1))

    def american_odds_to_decimal(self, odds):
        if odds > 0:
            return round(odds / 100 + 1, 2)
        else:
            return round(100 / -(odds) + 1, 2)

    def prob_to_decimal_odds(self, prob):
        return round((1/prob), 2)

    def update_odds(self, bet_odds):
        pass

    def round_to_nearest_multiple(self, x, base=5):
        return base * round(x / base)

    def format_american(self, odds):
        if odds > 0:
            return "+{}".format(odds)
        return odds

    def adjust_line(self, game):
        # gather how much money on both sides would win
        # adjust the line to make sure we are slightly ahead on the other side
        winning1 = 0
        winning2 = 0
        wager1 = 0
        wager2 = 0

        bets = Bet.objects.filter(game=game)
        if bets.count() > 3:
            for bet in bets:
                odds1 = bet.odds.decimal_odds.split('!')[0]
                odds2 = bet.odds.decimal_odds.split('!')[1]
                if game.players.split('-')[0] == bet.players:
                    winning1 += self.calculate_decimal_odds_winnings(odds1, bet.wager)
                    wager1 += bet.wager
                else:
                    winning2 += self.calculate_decimal_odds_winnings(odds2, bet.wager)
                    wager2 += bet.wager

            print("Game {} winnings1 {} winnings2 {}".format(game.gameid, winning1, winning2))
            # we must have a default value even if no one bet on either team
            if winning1 == 0:
                wager1 = 5
            if winning2 == 0:
                wager2 = 5

            print("Before adjustment Game {} winnings1 {} winnings2 {} wager1 {} wager2 {}".format(game.gameid, winning1, winning2, wager1, wager2))
            if winning1 < winning2:
                # winning2 > winning1 means there is more money on the second line...


                odds_to_change = odds1
                bottom_line = odds1
                top_line = odds2
            else:
                odds_to_change = odds2
                bottom_line = odds2
                top_line = odds1

            print("Before adjustment Game {}, odds_to_change {} bottom_line {} top_line {}".format(game.gameid, odds_to_change, bottom_line, top_line))
            line_adjusted = False
            return

            new_odds1 = odds1
            new_odds2 = odds2
            new_odds = odds_to_change
            while not line_adjusted:
                if odds_to_change > 2:
                    # move the odds +
                    new_odds += 0.01
                else:
                    # move the odds -
                    new_odds -= 0.01

                new_winnings1 = self.calculate_decimal_odds_winnings(new_odds1, bet.wager)
                print("Adjusting line. New odds for odds_to_change {}, {} produces winning1 {} and winning2 {}".format(odds_to_change, new_odds))

    def finish_game(self, game):
        # pay out all bets for this game
        if game.winning_team and game.is_finished:
            if game.winning_team.id == int(game.teams.split('.')[0]):
                winning_players = game.players.split('-')[0]
            else:
                winning_players = game.players.split('-')[1]

            bets = Bet.objects.filter(game=game)
            for bet in bets:
                if bet.players == winning_players:
                    bet.winnings = self.calculate_decimal_odds_winnings(bet.odds.decimal_odds, bet.wager)
                else:
                    bet.winnings = 0
                bet.save()

                bet.player.bankroll += bet.winnings
                bet.player.save()


    def create_new_bet(self, wager, player, team_odds):
        # first we need to see which team the bet is on
        wager = int(wager)

        # players are the list of players the bet is on
        # the bet the player gets is based on the last odds we see
        players = team_odds.players
        decimal_odds = team_odds.decimal_odds
        american_odds = team_odds.american_odds
        winnings = self.calculate_decimal_odds_winnings(decimal_odds, wager)
        bet = Bet(players=players, gameid=team_odds.bet_game.game.gameid, game=team_odds.bet_game.game, current_odds=team_odds, decimal_odds=decimal_odds, american_odds=american_odds, player=player, wager=wager, winnings=winnings, placed=True)
        bet.save()

        player.bankroll -= wager
        player.save()
        return bet

    '''
    Creates a new BetOdds object that serves as the initial line for the game
    '''
    def create_initial_odds_for_game(self, game, ratings1, ratings2):
        try:
            # get the ratings from the players in the game
            probs = self.probability_to_win(ratings1, ratings2)
            probs1 = probs[0]
            probs2 = probs[1]

            log_cb_msg("Initial probabilities for gameid {}: {}% to {}%".format(game.gameid, probs1, probs2))
            probability = "{}!{}".format(probs1, probs2)

            decimal1 = self.prob_to_decimal_odds(probs1)
            decimal2 = self.prob_to_decimal_odds(probs2)

            log_cb_msg("Decimal odds for gameid {}: {} {}".format(game.gameid, decimal1, decimal2))

            american1 = self.decimal_odds_to_american(decimal1)
            american2 = self.decimal_odds_to_american(decimal2)

            # round the american to the nearest 5 or 0, and change that back into decimal
            log_cb_msg("American odds for gameid {} before rounding: {} {}".format(game.gameid, american1, american2))
            american1 = self.round_to_nearest_multiple(american1)
            american2 = self.round_to_nearest_multiple(american2)
            american_odds = "{}!{}".format(american1, american2)

            log_cb_msg("American odds for gameid {}: {}".format(game.gameid, american_odds))

            decimal1 = self.american_odds_to_decimal(american1)
            decimal2 = self.american_odds_to_decimal(american2)
            decimal_odds = "{}!{}".format(decimal1, decimal2)
            log_cb_msg("Decimal odds for gameid {}: {}".format(game.gameid, decimal_odds))

            bet_game = BetGameOdds(gameid=game.id, game=game, players=game.players, initial=True, decimal_odds=decimal_odds, probability=probability, american_odds=american_odds)
            bet_game.save()

            players1 = game.players.split('-')[0]
            players2 = game.players.split('-')[1]
            team_odds1 = BetTeamOdds(bet_game=bet_game, players_index=0, decimal_odds=decimal1, american_odds=american1, players=players1)
            team_odds1.save()

            team_odds2 = BetTeamOdds(bet_game=bet_game, players_index=1, decimal_odds=decimal2, american_odds=american2, players=players2)
            team_odds2.save()

            log_cb_msg("Created initial odds for gameid {}".format(game.gameid))
        except:
            log_exception()

    def get_initial_bet_card(self, bet_game, emb):
        # grab the player list
        team1 = get_team_data_no_clan_player_list(bet_game.players.split('-')[0].split('.'))
        team2 = get_team_data_no_clan_player_list(bet_game.players.split('-')[1].split('.'))

        # grab both the american and decimal odds
        american1 = bet_game.american_odds.split('!')[0]
        american1 = self.format_american(int(american1))
        american2 = bet_game.american_odds.split('!')[1]
        american2 = self.format_american(int(american2))

        dec1 = bet_game.decimal_odds.split('!')[0]
        dec2 = bet_game.decimal_odds.split('!')[1]

        team_text = ""
        team_odds1 = BetTeamOdds.objects.filter(bet_game=bet_game, players_index=0)
        if team_odds1:
            id1 = team_odds1[0].id
        else:
            id1 = 0

        team_odds2 = BetTeamOdds.objects.filter(bet_game=bet_game, players_index=1)
        if team_odds2:
            id2 = team_odds2[0].id
        else:
            id2 = 0

        if int(american1) < int(american2):
            team_text += "[**{}**] {} ({}/{})\n".format(id1, team1, american1, dec1)
            team_text += "[**{}**] {} ({}/{})\n".format(id2, team2, american2, dec2)
        else:
            team_text += "[**{}**] {} ({}/{})\n".format(id2, team2, american2, dec2)
            team_text += "[**{}**] {} ({}/{})\n".format(id1, team1, american1, dec1)

        emb.add_field(name="Lines", value=team_text, inline=True)

        game_info_text = "[Game Link]({})".format(bet_game.game.game_link)
        emb.add_field(name="Game Info", value=game_info_text)

        help_info_text = "bb!bet {} 20 - bet 20 coins on {}\n".format(id1, team1)
        help_info_text += "bb!bet {} 20 - bet 5 coins on {}".format(id2, team2)
        emb.add_field(name="Betting Help", value=help_info_text)
        emb.title = "Opening lines for Game {}".format(bet_game.gameid)

        return emb

    def get_bet_results_card(self, bet_game, emb):
        bets = Bet.objects.filter(game=bet_game.game, winnings__gt=0)
        if bets.count() == 0:
            return None

        # grab the player list
        team1 = get_team_data_no_clan_player_list(bet_game.players.split('-')[0].split('.'))
        team2 = get_team_data_no_clan_player_list(bet_game.players.split('-')[1].split('.'))

        # grab both the american and decimal odds
        american1 = bet_game.american_odds.split('!')[0]
        american1 = self.format_american(int(american1))
        american2 = bet_game.american_odds.split('!')[1]
        american2 = self.format_american(int(american2))

        team_odds1 = BetTeamOdds.objects.filter(bet_game=bet_game, players_index=0)
        if team_odds1:
            id1 = team_odds1[0].id
        else:
            id1 = 0

        team_odds2 = BetTeamOdds.objects.filter(bet_game=bet_game, players_index=1)
        if team_odds2:
            id2 = team_odds2[0].id
        else:
            id2 = 0

        team_text = ""
        if int(american1) < int(american2):
            team_text += "[**{}**] {}\n".format(id1, team1)
            team_text += "[**{}**] {}\n".format(id2, team2)
        else:
            team_text += "[**{}**] {}\n".format(id2, team2)
            team_text += "[**{}**] {}\n".format(id1, team1)

        results_text = ""
        for bet in bets:
            results_text += "{} won {}\n".format(bet.player.name, bet.winnings)
        emb.add_field(name="Lines", value=team_text)
        emb.add_field(name="Results", value=results_text)
        emb.title = "Betting Results for Game {}".format(bet_game.gameid)

        return emb

class CLOTBookAdmin(admin.ModelAdmin):
    pass

admin.site.register(CLOTBook, CLOTBookAdmin)

class DiscordChannelCLOTBookLink(models.Model):
    channelid = models.BigIntegerField(default=0, blank=True, null=True, db_index=True)
    discord_user = models.ForeignKey('DiscordUser', blank=True, null=True, on_delete=models.DO_NOTHING)


class DiscordChannelCLOTBookLinkAdmin(admin.ModelAdmin):
    pass

admin.site.register(DiscordChannelCLOTBookLink, DiscordChannelCLOTBookLinkAdmin)


class Bet(models.Model):
    gameid = models.BigIntegerField(default=0, db_index=True)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE, blank=True, null=True)
    players = models.CharField(max_length=255, default="")
    created_time = models.DateTimeField(default=timezone.now)
    current_odds = models.ForeignKey('BetTeamOdds', on_delete=models.CASCADE, blank=True, null=True)
    american_odds = models.IntegerField(default=0)
    decimal_odds = models.FloatField(default=0.0)
    wager = models.IntegerField(default=0)
    player = models.ForeignKey('Player', on_delete=models.CASCADE, blank=True, null=True)
    placed = models.BooleanField(default=False)
    winnings = models.IntegerField(default=0)

class BetAdmin(admin.ModelAdmin):
    raw_id_fields = ['game', 'current_odds']

admin.site.register(Bet, BetAdmin)

class BetTeamOdds(models.Model):
    players = models.CharField(max_length=255, default="")
    decimal_odds = models.FloatField(default=0.0)
    american_odds = models.IntegerField(default=0)
    created_time = models.DateTimeField(default=timezone.now)
    players_index = models.IntegerField(default=-1)
    bet_game = models.ForeignKey('BetGameOdds', on_delete=models.CASCADE, blank=True, null=True)

class BetTeamOddsAdmin(admin.ModelAdmin):
    raw_id_fields = ['bet_game']

admin.site.register(BetTeamOdds, BetTeamOddsAdmin)

class BetGameOdds(models.Model):
    gameid = models.BigIntegerField(default=0, db_index=True)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE, blank=True, null=True)
    players = models.CharField(max_length=255, default="")
    decimal_odds = models.CharField(max_length=255, default="")
    american_odds = models.CharField(max_length=255, default="")
    created_time = models.DateTimeField(default=timezone.now)
    initial = models.BooleanField(default=False)
    probability = models.CharField(max_length=255, default="")
    sent_created_notification = models.BooleanField(default=False)
    sent_finished_notification = models.BooleanField(default=False)

class BetGameOddsAdmin(admin.ModelAdmin):
    raw_id_fields = ['game']

admin.site.register(BetGameOdds, BetGameOddsAdmin)