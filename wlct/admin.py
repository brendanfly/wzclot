from django.contrib import admin
from django.contrib.admin import ModelAdmin, SimpleListFilter
from wlct.logging import LogLevel, Logger, TournamentGameLog, TournamentGameStatusLog, TournamentLog, ProcessGameLog, ProcessNewGamesLog
from wlct.tournaments import Tournament, SwissTournament, GroupStageTournament, GroupStageTournamentGroup, RoundRobinTournament, SeededTournament, MonthlyTemplateRotation, MonthlyTemplateRotationMonth, TournamentGame, TournamentTeam, TournamentGameEntry, TournamentRound, TournamentInvite, TournamentPlayer, PromotionalRelegationLeague, PromotionalRelegationLeagueSeason, ClanLeague, ClanLeagueDivision, ClanLeagueTournament, ClanLeagueDivisionClan, ClanLeagueTemplate, RealTimeLadderTemplate, RealTimeLadder, PromotionalRelegationLeagueTournament, RealTimeLadderVeto

class LogFilter(SimpleListFilter):
    title = 'Log Level' # a label for our filter
    parameter_name = 'loglevel' # you can put anything here

    def lookups(self, request, model_admin):
      # This is where you create filter options; we have two:
      # also loop through all tournaments and display those IDs here
        return [
            ('informational', 'Informational'),
            ('critical', 'Critical'),
            ('error', 'Errors'),
            ('warning', 'Warning'),
            ('tournament', 'Tournament'),
            ('tournament_game', 'Tournament Game'),
            ('tournament_game_status', 'Tournament Game Status'),
            ('engine', 'Engine'),
            ('bot', 'Bot'),
            ('clean_logs', 'Log Cleanup')
        ]

    def queryset(self, request, queryset):
        # This is where you process parameters selected by use via filter options:
        if self.value() == 'informational':
            # Get websites that have at least one page.
            return queryset.distinct().filter(level=LogLevel.informational)
        if self.value() == 'critical':
            # Get websites that don't have any pages.
            return queryset.distinct().filter(level=LogLevel.critical)
        if self.value() == 'warning':
            return queryset.distinct().filter(level=LogLevel.warning)
        if self.value() == 'error':
            return queryset.distinct().filter(level=LogLevel.error)
        if self.value() == 'engine':
            return queryset.distinct().filter(level=LogLevel.engine)
        if self.value() == 'bot':
            return queryset.distinct().filter(level=LogLevel.bot)
        if self.value() == 'clean_logs':
            return queryset.distinct().filter(level=LogLevel.clean_logs)


class LogAdmin(admin.ModelAdmin):
    list_filter = (LogFilter, )
    search_fields = ['msg', 'level', 'timestamp']

admin.site.register(Logger, LogAdmin)


class ProcessGameLogAdmin(admin.ModelAdmin):
    search_fields = ['timestamp', 'game__id', 'game__gameid']
    raw_id_fields = ['game']

admin.site.register(ProcessGameLog, ProcessGameLogAdmin)


class ProcessNewGamesLogAdmin(admin.ModelAdmin):
    search_fields = ['tournament__id']
    raw_id_fields = ['tournament']

admin.site.register(ProcessNewGamesLog, ProcessNewGamesLogAdmin)


class TournamentLogAdmin(admin.ModelAdmin):
    search_fields = ['tournament__id']
    raw_id_fields = ['tournament']

admin.site.register(TournamentLog, TournamentLogAdmin)


class TournamentGameStatusLogAdmin(admin.ModelAdmin):
    search_fields = ['tournament__id', 'timestamp', 'game__id', 'game__gameid']
    raw_id_fields = ['tournament', 'game']

admin.site.register(TournamentGameStatusLog, TournamentGameStatusLogAdmin)


# Register admin models here
class TournamentAdmin(admin.ModelAdmin):
    raw_id_fields = ['created_by', 'winning_team']


admin.site.register(Tournament, TournamentAdmin)


class TournamentGameLogAdmin(admin.ModelAdmin):
    search_fields = ['game__gameid', 'game__id']
    raw_id_fields = ['tournament', 'game']

admin.site.register(TournamentGameLog, TournamentGameLogAdmin)


class SwissTournamentAdmin(admin.ModelAdmin):
    pass


admin.site.register(SwissTournament, SwissTournamentAdmin)

class SeededTournamentAdmin(admin.ModelAdmin):
    pass


admin.site.register(SeededTournament, SeededTournamentAdmin)

class GroupStageTournamentAdmin(admin.ModelAdmin):
    pass


admin.site.register(GroupStageTournament, GroupStageTournamentAdmin)

class GroupStageTournamentGroupAdmin(admin.ModelAdmin):
    pass

admin.site.register(GroupStageTournamentGroup, GroupStageTournamentGroupAdmin)

class RoundRobinTournamentAdmin(admin.ModelAdmin):
    raw_id_fields = ['parent_tournament', 'winning_team', 'first_place', 'second_place']

admin.site.register(RoundRobinTournament, RoundRobinTournamentAdmin)

class TournamentRoundAdmin(admin.ModelAdmin):
    pass


admin.site.register(TournamentRound, TournamentRoundAdmin)

class TournamentTeamAdmin(admin.ModelAdmin):
    search_fields = ['id', 'tournament__name']


admin.site.register(TournamentTeam, TournamentTeamAdmin)

class TournamentGameEntryAdmin(admin.ModelAdmin):
    pass

admin.site.register(TournamentGameEntry, TournamentGameEntryAdmin)


class TournamentGameAdmin(admin.ModelAdmin):
    search_fields = ['gameid', 'id']
    raw_id_fields = ['winning_team', 'tournament']

admin.site.register(TournamentGame, TournamentGameAdmin)


class TournamentPlayerAdmin(admin.ModelAdmin):
    search_fields = ['player__token', 'tournament__name']


admin.site.register(TournamentPlayer, TournamentPlayerAdmin)

class TournamentInviteAdmin(admin.ModelAdmin):
    pass

admin.site.register(TournamentInvite, TournamentInviteAdmin)

class MonthlyTemplateRotationMonthAdmin(admin.ModelAdmin):
    pass

admin.site.register(MonthlyTemplateRotationMonth, MonthlyTemplateRotationMonthAdmin)

class MonthlyTemplateRotationAdmin(admin.ModelAdmin):
    pass

admin.site.register(MonthlyTemplateRotation, MonthlyTemplateRotationAdmin)

class PromotionalRelegationLeagueAdmin(admin.ModelAdmin):
    raw_id_fields = ['created_by', 'winning_team']
    search_fields = ['name', 'id']

admin.site.register(PromotionalRelegationLeague, PromotionalRelegationLeagueAdmin)

class PromotionalRelegationLeagueSeasonAdmin(admin.ModelAdmin):
    search_fields = ['name', 'id']
    raw_id_fields = ['created_by', 'winning_team']

admin.site.register(PromotionalRelegationLeagueSeason, PromotionalRelegationLeagueSeasonAdmin)

class PromotionalRelegationLeagueTournamentAdmin(admin.ModelAdmin):
    search_fields = ['name', 'id']
    raw_id_fields = ['created_by', 'winning_team', 'first_place', 'second_place', 'division', 'parent_tournament']

admin.site.register(PromotionalRelegationLeagueTournament, PromotionalRelegationLeagueTournamentAdmin)


class ClanLeagueAdmin(admin.ModelAdmin):
    pass

admin.site.register(ClanLeague, ClanLeagueAdmin)

class ClanLeagueDivisionAdmin(admin.ModelAdmin):
    pass

admin.site.register(ClanLeagueDivision, ClanLeagueDivisionAdmin)

class ClanLeagueDivisionClanAdmin(admin.ModelAdmin):
    pass

admin.site.register(ClanLeagueDivisionClan, ClanLeagueDivisionClanAdmin)

class ClanLeagueTournamentAdmin(admin.ModelAdmin):
    raw_id_fields = ['created_by', 'winning_team', 'first_place', 'second_place', 'division', 'clan_league_template', 'parent_tournament']

admin.site.register(ClanLeagueTournament, ClanLeagueTournamentAdmin)

class ClanLeagueTemplateAdmin(admin.ModelAdmin):
    pass

admin.site.register(ClanLeagueTemplate, ClanLeagueTemplateAdmin)

class RealTimeLadderAdmin(admin.ModelAdmin):
    pass

admin.site.register(RealTimeLadder, RealTimeLadderAdmin)

class RealTimeLadderTemplateAdmin(admin.ModelAdmin):
    pass

admin.site.register(RealTimeLadderTemplate, RealTimeLadderTemplateAdmin)

class RealTimeLadderVetoAdmin(admin.ModelAdmin):
    raw_id_fields = ['team']

admin.site.register(RealTimeLadderVeto, RealTimeLadderVetoAdmin)