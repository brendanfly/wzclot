from django.db import models
from django.utils import timezone
from wlct.models import Player
from django.contrib import admin
from wlct.logging import log_cb_msg, log_exception

# Models for the Off-site betting for the CLOT
def get_clotbook():
    cb = CLOTBook.objects.all()
    if cb.count() == 1:
        return cb[0]
    else:
        cb = CLOTBook()
        cb.save()
        return cb

class CLOTBook(models.Model):
    total_bets = models.BigIntegerField(default=0)
    in_progress_bets = models.BigIntegerField(default=0)

    currency_name = "Nohams"

    # always gives the probability to win for ratings1 based on the opponents of ratings2
    def probability_to_win(self, ratings1, ratings2):
        if ratings1 == ratings2:
            favorite = ratings1
            underdog = ratings2
        else:
            favorite = ratings1 if ratings1 > ratings2 else ratings2
            underdog = ratings1 if ratings1 < ratings2 else ratings2
        prob_win = round((1 / ((10*(favorite-underdog)/400) + 1)), 2)

        if underdog == ratings1:
            prob_win = 1-prob_win
        print("Probability: Favorite: {}/{}, Underdog {}/{}".format(favorite, prob_win, underdog, 1-prob_win))
        return prob_win

    def create_new_bet(self, wager, player, game):
        pass

    def calculate_decimal_odds_winnings(self, odds, wager):
        # winnings are calculated based on the wager and the current odds
        # ex. odds of -105 means you'd have to bet 100 to win 105
        return (wager*odds)-wager

    def calculate_american_odds_winnings(self, odds, wager):
        odds = self.american_odds_to_decimal(odds)
        return self.calculate_decimal_odds_winnings(odds, wager)

    def decimal_odds_to_american(self, odds):
        if odds > 2.0:
            return (odds-1)*100
        else:
            return -100 // (odds-1)

    def american_odds_to_decimal(self, odds):
        if odds > 0:
            return odds // 100 + 1
        else:
            return 100 // odds + 1

    def prob_to_decimal_odds(self, prob):
        return (1/prob)

    def update_odds(self, bet_odds):
        pass

    def round_to_nearest_multiple(self, x, base=5):
        return base * round(x / base)

    '''
    Creates a new BetOdds object that serves as the initial line for the game
    '''
    def create_initial_odds_for_game(self, game, ratings1, ratings2):
        try:
            # get the ratings from the players in the game
            probs1 = self.probability_to_win(ratings1, ratings2)
            probs2 = self.probability_to_win(ratings2, ratings1)

            log_cb_msg("Initial odds for gameid {}: {}% to {}%".format(game.gameid, probs1, probs2))
            probability = "{}.{}".format(probs1, probs2)

            decimal1 = self.prob_to_decimal_odds(probs1)
            decimal2 = self.prob_to_decimal_odds(probs2)
            decimal_odds = "{}.{}".format(decimal1, decimal2)
            log_cb_msg("Decimal odds for gameid {}: {}".format(game.gameid, decimal_odds))

            american_odds = "{}.{}".format(self.decimal_odds_to_american(decimal1), self.decimal_odds_to_american(decimal2))
            log_cb_msg("American odds for gameid {}: {}".format(game.gameid, american_odds))

            odds = BetOdds(gameid=game.id, game=game, players=game.players, initial=True, decimal_odds=decimal_odds, probability=probability, american_odds=american_odds)
            odds.save()

            log_cb_msg("Created initial odds for gameid {}".format(game.gameid))
        except:
            log_exception()

class CLOTBookAdmin(admin.ModelAdmin):
    pass

admin.site.register(CLOTBook, CLOTBookAdmin)

class DiscordChannelCLOTBookLink(models.Model):
    channelid = models.BigIntegerField(default=0, blank=True, null=True, db_index=True)
    discord_user = models.ForeignKey('DiscordUser', blank=True, null=True, on_delete=models.CASCADE)


class DiscordChannelCLOTBookLinkAdmin(admin.ModelAdmin):
    pass

admin.site.register(DiscordChannelCLOTBookLink, DiscordChannelCLOTBookLinkAdmin)


class Bet(models.Model):
    gameid = models.BigIntegerField(default=0, db_index=True)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE, blank=True, null=True)
    players = models.CharField(max_length=255, default="")
    created_time = models.DateTimeField(default=timezone.now)
    odds = models.ForeignKey('BetOdds', on_delete=models.CASCADE, blank=True, null=True)

class BetAdmin(admin.ModelAdmin):
    raw_id_fields = ['game', 'odds']


admin.site.register(Bet, BetAdmin)

class BetOdds(models.Model):
    gameid = models.BigIntegerField(default=0, db_index=True)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE, blank=True, null=True)
    players = models.CharField(max_length=255, default="")
    decimal_odds = models.CharField(max_length=255, default="")
    american_odds = models.CharField(max_length=255, default="")
    created_time = models.DateTimeField(default=timezone.now)
    initial = models.BooleanField(default=False)
    probability = models.CharField(max_length=255, default="")
    sent_notification = models.BooleanField(default=False)


class BetOddsAdmin(admin.ModelAdmin):
    raw_id_fields = ['game']

admin.site.register(BetOdds, BetOddsAdmin)