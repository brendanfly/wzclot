from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib import admin
from django.utils import timezone
from wlct.api import API
from wlct.logging import log, LogLevel

invalid_token_string = "invalid"
invalid_clan_string = "clan+#!invalid"
invalid_name_string = "missing no"

# Default User Model
# Custom user model using the default authentication implementation
class User(AbstractUser):
    pass

'''
Discord specific models. 
'''
class DiscordUser(models.Model):
    memberid = models.BigIntegerField(default=0, blank=True, null=True, db_index=True, unique=True)
    link_mention = models.BooleanField(default=False, blank=True, null=True)

    def __str__(self):
        return "Member: {}, LinkMention: {}".format(self.memberid, self.link_mention)

class DiscordChannelTournamentLink(models.Model):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE, blank=True, null=True)
    channelid = models.BigIntegerField(default=0, blank=True, null=True, db_index=True)
    discord_user = models.ForeignKey('DiscordUser', blank=True, null=True, on_delete=models.DO_NOTHING)
    name = models.CharField(default="", blank=True, null=True, max_length=150)

    def does_game_pass_filter(self, game):
        player_filters = DiscordChannelPlayerFilter.objects.filter(link=self)
        clan_filters = DiscordChannelClanFilter.objects.filter(link=self)

        # If no filters found, game can be used
        if not player_filters and not clan_filters:
            return True

        player_tokens = game.get_player_tokens()
        players = Player.objects.none()

        # Get all players to compare with filters
        for team in player_tokens:
            for player in team:
                players |= Player.objects.filter(token=player)

        # Check if any filters pass against the player/clans in game
        for player in players:
            player_filters_found = DiscordChannelPlayerFilter.objects.filter(link=self, player=player)
            clan_filters_found = DiscordChannelClanFilter.objects.filter(link=self, clan=player.clan)

            # Game passes filter if any results are returned
            if player_filters_found or clan_filters_found:
                return True
        return False

    def __str__(self):
        link_str = "Link for tournament {}".format(self.tournament.name)
        if self.name:
            link_str += " to {}".format(self.name)

        return link_str

# class to track text updates the bot will send out a single-time to channels linked to the tournament
class DiscordTournamentUpdate(models.Model):
    update_text = models.TextField(default="", blank=True, null=True)
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE, blank=True, null=True)
    bot_send = models.BooleanField(default=False)

# class to track clan filters for game log updates
class DiscordChannelClanFilter(models.Model):
    link = models.ForeignKey('DiscordChannelTournamentLink', on_delete=models.DO_NOTHING, blank=True, null=True)
    clan = models.ForeignKey('Clan', on_delete=models.CASCADE, blank=True, null=True)

# class to track player filters for game log updates
class DiscordChannelPlayerFilter(models.Model):
    link = models.ForeignKey('DiscordChannelTournamentLink', on_delete=models.DO_NOTHING, blank=True, null=True)
    player = models.ForeignKey('Player', on_delete=models.CASCADE, blank=True, null=True)

class Engine(models.Model):
    last_run_time = models.DateTimeField(default=timezone.now)
    next_run_time = models.DateTimeField(blank=True, null=True)
    update_elo_scores_500 = models.BooleanField(default=False)

class Clan(models.Model):
    name = models.CharField(max_length=64, default=invalid_clan_string, db_index=True)
    icon_link = models.CharField(max_length=255, default=invalid_clan_string)
    image_path = models.CharField(max_length=255, default=invalid_clan_string)

    def __str__(self):
        return self.name

    def update_player_clans(self):
        players = Player.objects.filter(clan=self)
        update_player_clans(players)

class ClanAdmin(admin.ModelAdmin):
    pass


admin.site.register(Clan, ClanAdmin)


class TournamentAdministrator(models.Model):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    player = models.ForeignKey('Player', on_delete=models.CASCADE)

class TournamentAdministratorAdmin(admin.ModelAdmin):
    pass

admin.site.register(TournamentAdministrator, TournamentAdministratorAdmin)

class Player(models.Model):
    token = models.CharField(max_length=32, default=invalid_token_string, db_index=True)
    name = models.CharField(max_length=64, default=invalid_name_string, db_index=True)
    clan_text = models.CharField(max_length=64, default=invalid_clan_string)
    clan = models.ForeignKey('Clan', blank=True, null=True, on_delete=models.SET_NULL)
    is_on_vacation = models.BooleanField(default=False, blank=True, null=True)
    bot_token = models.CharField(max_length=34, default=invalid_token_string, db_index=True)
    discord_member = models.ForeignKey('DiscordUser', blank=True, null=True, on_delete=models.CASCADE, related_name='discord')
    rating = models.IntegerField(default=1500)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    bankroll = models.IntegerField(default=100)

    def set_player_data(self, token, playerData):
        self.token = token
        self.clan_text = playerData['clan']
        self.name = playerData['name']


    def logout(self):
        self.token = None


    def __str__(self):
        if self.discord_member:
            return self.name + "({}), discord id: {}".format(self.token, self.discord_member.memberid)
        else:
            return self.name + "({})".format(self.token)

def update_player_clans(players, engine=None):
    api = API()

    for player in players:
        try:
            if engine and engine.shutdown:
                return

            # Get player info
            p_data = api.api_validate_invite_token(player.token).json()

            if "name" in p_data and p_data["name"] != player.name:
                # Update player name if it has changed
                log("Updated name for player: {} ({}) to {}".format(player.name, player.token, p_data["name"]), LogLevel.engine)
                player.name = p_data["name"]
                player.save()
            if "clan" in p_data:
                # If clan exists, check if matches clan on player object
                clan = Clan.objects.filter(name=p_data["clan"])
                if clan and clan[0] != player.clan:
                    log("Updated clan for player: {} ({}) to {}".format(player.name, player.token, clan[0].name), LogLevel.engine)
                    player.clan = clan[0]
                    player.clan_text = clan[0].name
                    player.save()
            else:
                # Player is not in clan... Remove clan from player obj if exists
                if player.clan:
                    log("Updated clan for player: {} ({}) to None".format(player.name, player.token), LogLevel.engine)
                    player.clan = None
                    player.clan_text = ""
                    player.save()
        except:
            continue

class PlayerAdmin(admin.ModelAdmin):
    search_fields = ['name', 'token', 'clan__name']

admin.site.register(Player, PlayerAdmin)

# Default User Admin
class UserAdmin(admin.ModelAdmin):
    pass

admin.site.register(User, UserAdmin)

class DiscordUserAdmin(admin.ModelAdmin):
    pass

admin.site.register(DiscordUser, DiscordUserAdmin)

class DiscordChannelTournamentLinkAdmin(admin.ModelAdmin):
    pass

admin.site.register(DiscordChannelTournamentLink, DiscordChannelTournamentLinkAdmin)

class DiscordTournamentUpdateAdmin(admin.ModelAdmin):
    pass

admin.site.register(DiscordTournamentUpdate, DiscordTournamentUpdateAdmin)