from django.urls import include, path
from django.contrib import admin
from django.contrib.auth import views as auth_views
admin.autodiscover()
import debug_toolbar
import wlct.views

# Examples:
# url(r'^$', 'wltourney.views.home', name='home'),
# url(r'^blog/', include('blog.urls')),

urlpatterns = [
    # site specific URLs, which is mainly the admin site for now
    path('admin/', admin.site.urls),

    #debug toolbar urls
    path('__debug__/', include(debug_toolbar.urls)),

    # wlct app specific URLS
    path('', wlct.views.index),
    path('index/', wlct.views.index, name='index'),
    path('login/', wlct.views.login_view, name='login'),
    path('about/', wlct.views.about_view, name='about_view'),
    path('games/', wlct.views.mygames_view, name='mygames_view'),
    path('me/', wlct.views.settings_view, name='settings_view'),
    path('me/generate/', wlct.views.settings_generate_clot_token_view, name='settings_generate_clot_token_view'),
    path('stats/<int:token>', wlct.views.stats_view, name='stats_player_view'),
    path('stats/', wlct.views.stats_view, name='stats_clot_view'),

    # tournament related urls
    path('tournaments/create/', wlct.views.create_new_view, name='create_new_tourney_view'),
    path('tournaments/create/<int:type>/', wlct.views.create_new_view, name='create_new_tourney_specific_view'),
    path('tournaments/submit/', wlct.views.create_new_form_submit_view, name='create_new_form_submit_view'),
    path('tournaments/player_status_change/', wlct.views.tournament_player_status_change, name='tournament_player_status_change'),
    path('tournaments/refresh/', wlct.views.refresh_tournament, name='tournament_refresh'),
    path('tournaments/template_check/', wlct.views.template_check_view, name='template_check_view'),
    path('tournaments/me/', wlct.views.mytourneys_view, name='mytourneys_view'),
    path('tournaments/<int:id>/', wlct.views.tournament_display_view, name='tournament_display_view'),
    path('tournaments/start/', wlct.views.tournament_start, name='tournament_start'),
    path('tournaments/start_request/', wlct.views.tournament_start_request, name='tournament_start_request'),
    path('tournaments/cancel_request/', wlct.views.tournament_cancel_request, name='tournament_cancel_request'),
    path('tournaments/delete/', wlct.views.tournament_delete, name='tournament_delete'),
    path('tournaments/invite_players/', wlct.views.tournament_invite_players, name='tournament_invite_players'),

    # league related URLs
    path('leagues/create/', wlct.views.create_new_league_view, name='create_new_league_view'),
    path('leagues/create/<str:encoded_url>/', wlct.views.create_new_league_specific_view, name='create_new_league_specific_view'),
    path('leagues/<int:id>/', wlct.views.league_display_view, name='league_display_view'),
    path('leagues/league_editor/', wlct.views.league_editor_view, name='league_editor_view'),
    path('leagues/submit_editing_window/', wlct.views.league_submit_editing_window, name='league_submit_editing_window'),
    path('leagues/update_status/', wlct.views.league_update_status, name='league_update_status'),

    path('cl/divisions/update/', wlct.views.cl_update_divisions, name='cl_update_divisions'),
    path('cl/templates/update/', wlct.views.cl_update_templates, name='cl_update_templates'),
    path('cl/templates/start/', wlct.views.cl_start_template, name='cl_start_template'),

    path('pr/seasons/update/', wlct.views.pr_update_season, name="pr_update_season"),
    path('pr/season/<int:id>/', wlct.views.pr_view_season, name="pr_view_season"),

    path('max_games_at_once/', wlct.views.update_max_games_at_once, name='update_max_games_at_once'),

    path('github/webhook/', wlct.views.webhook_request, name='webhook_request'),

    # URLs for the APIs that expose read/writing data back and forth
    # TBD
]
