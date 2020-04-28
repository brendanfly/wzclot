/* =================================
------------------------------------
	Main file with JS functionality for the WL Tourney website
	Version: 1.0
 ------------------------------------
 ====================================*/

// Update the count down every 1 second

function handle_game_countdown(obj)
{
    // Set the date we're counting down to
    var dateStr = obj.text() + " UTC";
    var countDownDate = new Date(dateStr).getTime();
    var x = setInterval(function()
    {

        // Get today's date and time
        var now = new Date().getTime();

        // Find the distance between now and the count down date
        var distance = countDownDate - now;

        if (distance < 0) {
            clearInterval(x);
            obj.text("EXPIRED");
        }
        else
        {
          // Time calculations for days, hours, minutes and seconds
          var days = Math.floor(distance / (1000 * 60 * 60 * 24));
          var hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
          var minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
          var seconds = Math.floor((distance % (1000 * 60)) / 1000);

          if (isNaN(days) || isNaN(hours) || isNaN(minutes) || isNaN(seconds))
          {
            obj.text("N/A");
          }
          else
          {
              // Display the result in the element with id="demo"
              obj.text(days + "d " + hours + "h " + minutes + "m " + seconds + "s ");
          }
        }
    }, 1000);
}

function onclick_seeded_match(data)
{
    try
    {
        var game_link_data = $('div#bracket_seeded_async').attr('data-game-links');
        var game_link_json = JSON.parse(game_link_data);
        window.location = game_link_json[data];
    }
    catch (e)
    {
        console.log(e);
    }
}

function handle_request(url, data, onSuccessFunc, onErrorFunc, onAlwaysFunc, onFailureFunc)
{
    $.ajax({
        type:"POST",
        url: url,
        headers: {'X-CSRFToken': Cookies.get('csrftoken')},
        data: data,
        success: function(data)
        {
            onSuccessFunc(data);
        },
        error: function(jqXHR, textStatus, errorThrown)
        {
            onErrorFunc(data);
        }
        }).always(function()
        {
            onAlwaysFunc();
        }).fail(function() {
            onFailureFunc();
        });
}

function show_spinning(obj, text)
{
    obj.prop('disabled', true);
    obj.html('<i class="fa fa-spinner fa-spin"></i> ' + text);
}

function remove_spinning(obj, old_text_value)
{
    obj.prop('disabled', false);
    obj.html(old_text_value);
}

function hook_invite_players()
{
    $(".invite_players").on('click', function() {
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);
        $("#tournament_invites").modal('show');
        $("#tournament_invites_text").html('<p><i class="fa fa-spinner fa-spin"></i>&nbsp;Loading player list...</p>');
        var tournamentid = $("#tournamentid").val();
        var data_attrib = thisVar.data();
        $.ajax({
            type:"POST",
            url:"/tournaments/invite_players/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'tournamentid' : tournamentid, 'data_attrib' : data_attrib},
            success: function(data)
            {
               if (data.success == "true")
               {
                    $("#invitetab").html(data.invited_players);

                    // now create a filter on the table to hide/show rows based on the filter text
                    $("#tournament_invites_text").html(data.invited_players_inverse);

                    $("#invite-filter").on("keyup", function() {
                        var value = $(this).val().toLowerCase();
                        $("#invite-filter-table tr").filter(function() {
                            $(this).toggle($(this).text().toLowerCase().indexOf(value) > -1)
                        });
                    });

                    if (data.can_start_tourney)
                    {
                        // We can now start the tournament, make sure the start button is enabled
                        $("#start_tournament").prop('disabled', false);
                    }
                    else
                    {
                        $("#start_tournament").prop('disabled', true);
                    }

                    $("#cl-update-player").data(thisVar.data());
                    hook_pr_buttons();
               }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                thisVar.html(old_text_value);
                thisVar.prop('disabled', false);
            },
        }).always(function()
            {
                thisVar.html(old_text_value);
                thisVar.prop('disabled', false);
            }).fail(function()
            {
                thisVar.html(old_text_value);
                thisVar.prop('disabled', false);
            });
    });
}

function hook_clan_league_buttons()
{
    $("button[id^=division-remove").on('click', function()
    {
        update_division("remove", jQuery(this));
    });

    $("button[id^=division-update").on('click', function()
    {
        update_division("update", jQuery(this));
    });

    $("a[id^=remove-clan").on('click', function()
    {
        update_division("remove-clan", jQuery(this));
    });

    $("a[id^=remove-template").on('click', function()
    {
        update_cl_templates("remove", jQuery(this));
    });


}

function update_cl_templates(type, obj)
{
    var tournamentid = $("#tournamentid").val();
    var old_text_value = obj.text();
    show_spinning(obj, "Saving...");
    data = {};
    var url = "/cl/templates/update/";

    if ($('#template-warning').length)
    {
        var r = confirm("WARNING: Altering template data for this season will erase all current divisions if # of players per team change.");
        if (r != true)
        {
            remove_spinning(obj, old_text_value);
            return;
        }
    }

    if (type == "add")
    {
        var players_per_team = $("#players_per_team").val();
        var templateid = $("#templateid").val();
        var templatesettings = $("#templatesettings").val();
        var templatename = $("#templatename").val();
        data = {"tournamentid" : tournamentid, "templateid": templateid, "players_per_team": players_per_team, "optype": type, "templatesettings" : templatesettings, "templatename" : templatename};
    }
    else if (type == "remove")
    {
        var templateid = obj.data('templateid');
        data = {"tournamentid" : tournamentid, "templateid": templateid, "optype": type};
    }

    handle_request(url, data,
        function(data) {
            // onSuccess
            // On success we need to use the data passed back
            if (data.success == "true")
            {
                // populate the new list of templates
                $("#templates").html(data.templates);
                $("#templateid").val('');
                $("#templatesettings").val('');
                $("#templatename").val('');
                hook_clan_league_buttons();
                hook_pr_buttons();
            }
            else
            {
                // display the error
                $("#form_status_text").html(data.error);
                $("#form_status").show();
            }
        },
        function (data) {
            // onError
            // display the error message

        },
        function () {
            // always
            remove_spinning(obj, old_text_value);
        },
        function () {
            remove_spinning(obj, old_text_value);
        });
}

function update_division(type, obj)
{
    var tournamentid = $("#tournamentid").val();
    var old_text_value = obj.text();
    show_spinning(obj, "Saving...");
    data = {};
    var url = "/cl/divisions/update/";
    if (type == "add")  // add a new division
    {
        // we need to display the div to create a new division, which is just text + a submit button
        // send the division information over via AJAX.
        data = {"tournamentid": tournamentid, "division-name": $("#division-name").val(), "optype" : "add"};
    }
    else if (type == "update")
    {
        // update the division, pass over clans + id
        // grab the list above us
        var newValues = '';
        obj.closest(".card-body").find("select").each(function() {
            newValues += '' + $(this).val();
        });
        var divisionid = obj.data("division");
        data = {"tournamentid" : tournamentid, "divisionid" : divisionid, "optype": "update", "clans": newValues};
    }
    else if (type == "remove-clan")
    {
         var clanid = obj.data('clan');
         var divisionid = obj.data('division');
         var clans = "";
         clans += clanid;
         data = {"tournamentid": tournamentid, "divisionid": divisionid, "optype": "remove-clan", "clans": clans};
    }
    else if (type == "remove")
    {
        // remove the division, pass over the id
        var divisionid = obj.data('division');
        data = {"tournamentid" : tournamentid, "divisionid" : divisionid, "optype": "remove"};
    }
    else if (type == "add-team")
    {
        var divisionid = obj.data('division');
        data = {"tournamentid" : tournamentid, "divisionid" : divisionid, "optype": "add-team"};
    }
    else if (type == "remove-team")
    {
        var divisionid = obj.data('division');
        var teamid = obj.data('team');
        data = {"tournamentid" : tournamentid, "divisionid" : divisionid, "optype": "remove-team", "teamid" : teamid};
    }

     handle_request(url, data,
        function(data) {
            // onSuccess
            // On success we need to use the data passed back
            if (data.success == "true")
            {
                // populate the new list of divisions
                $("#division_list").html(data.divisions);
                $("#division-name").val('');
                hook_clan_league_buttons();
                hook_pr_buttons();
                hook_invite_players();

                if (data.can_start_tourney)
                {
                    // We can now start the tournament, make sure the start button is enabled
                    $("#start_tournament").prop('disabled', false);
                }
                else
                {
                    $("#start_tournament").prop('disabled', true);
                }
            }
            else
            {
                // display the error
                $("#form_status_text").html(data.error);
                $("#form_status").show();
            }
        },
        function (data) {
            // onError
            // display the error message

        },
        function () {
            // always
            remove_spinning(obj, old_text_value);
        },
        function () {
            remove_spinning(obj, old_text_value);
        });
}

function show_copy_season_modal(obj)
{
    $('#copy-season-modal').modal('show');
    $('#copy-season-title').text(`Copy ${obj.data('id')}?`);
    $('#copy-season-button').data('id', obj.data('id'));
}

function update_pr_season(obj, type)
{
    var tournamentid = $("#tournamentid").val();
    var old_text_value = obj.text();
    var data = {"tournamentid": tournamentid, "type" : type};

    if (type == "add")
    {
        show_spinning(obj, "Creating New Season...");
        data["season-name"] = $("#season-name").val();
        data["games-at-once"] = $("#games-at-once").val();
    }
    else if (type == "remove")
    {
        show_spinning(obj, "Deleting Season...");
        data["season_id"] = obj.data('id');
    } else if (type == "copy") {
        data["season-name"] = $("#copy-season-name").val();
        data["season_id"] = obj.data('id');

    }
    var url = "/pr/seasons/update/";

    handle_request(url, data,
        function(data) {
            // onSuccess
            // On success we need to use the data passed back
            if (data.success == "true")
            {
                // populate the new list of seasons
                $("#pr-season-tab").html(data.season_data);
                $("#season-name").val('');
                $("#copy-season-modal").modal('hide');
                $("#copy-season-name").val('');
            }
            else
            {
                // display the error
                $("#form_status_text").html(data.error);
                $("#form_status").show();
            }
        },
        function (data) {
            // onError
            // display the error message
        },
        function () {
            // always
            remove_spinning(obj, old_text_value);
        },
        function () {
            remove_spinning(obj, old_text_value);
    });
}

function hook_pr_buttons()
{
    $("#create-pr-season").on('click', function()
    {
        update_pr_season(jQuery(this), "add");
    });

    $("#remove-pr-season").on('click', function()
    {
        update_pr_season(jQuery(this), "remove");
    });

    $("#copy-pr-season").on('click', function()
    {
        show_copy_season_modal(jQuery(this));
    });

    $("#copy-season-button").on('click', function()
    {
        update_pr_season(jQuery(this), "copy");
    });

    $("button[id^=division-add-team").on('click', function()
    {
        update_division("add-team", jQuery(this));
    });

    $("a[id^=division-remove-team").on('click', function()
    {
        update_division("remove-team", jQuery(this));
    });
}

function handle_player_status_change(obj, join)
{
    var tournamentid = $("#tournamentid").val();
    var templateid = $("#templateid").val();
    var old_text_value = obj.text();

    obj.prop('disabled', true);
    var text = "Leaving Tournament...";
    if (join)
    {
        text = "Joining Tournament...";
    }

    show_spinning(obj, text);
    // no need to parse the id, we can do that on the backend, just send the data over
    var id = obj.attr('id');
    var send_data = {'tournamentid' : tournamentid, 'templateid' : templateid, 'buttonid': id};

    if (typeof obj.data('team') !== 'undefined')
    {
        send_data['team'] = obj.data('team');
    }

    $.ajax({
        type:"POST",
        url:"/tournaments/player_status_change/",
        headers: {'X-CSRFToken': Cookies.get('csrftoken')},
        data: send_data,
        success: function(data)
        {
           if (data.success == "true")
           {
              // update the table, which should have been returned to us
              $("#lobbytab").html(data.team_table);
              hook_player_status_change();

              if (data.can_start_tourney)
              {
                    // We can now start the tournament, make sure the start button is enabled
                    $("#start_tournament").prop('disabled', false);
              }
              else
              {
                    $("#start_tournament").prop('disabled', true);
              }

              if (data.is_league)
              {
                  $("#join_leave_buttons").html(data.join_leave_buttons);
              }
           }
           else
           {
              // display the modal with the error
              $("#tournament_status_title").text("Tournament Error");
              $("#tournament_status_text").text(data.error);
              $("#tournament_status").modal("show");
           }
        },
        error: function(jqXHR, textStatus, errorThrown)
        {
            remove_spinning(obj, old_text_value);
        },
    }).always(function()
        {
            remove_spinning(obj, old_text_value);
        }).fail(function()
        {
            remove_spinning(obj, old_text_value);
        });
}

function hook_player_status_change()
{
    $('.player_status_change').on('click', function()
    {
        var decline = jQuery(this).data('action') === 'decline';
        handle_player_status_change(jQuery(this), !decline);
    });
}

function refresh_tournament_async()
{
    var tournamentid = $("#tournamentid").val();
    var templateid = $("#templateid").val();
    $.ajax({
        type:"POST",
        url:"/tournaments/refresh/",
        headers: {'X-CSRFToken': Cookies.get('csrftoken')},
        data: {'tournamentid' : tournamentid, 'templateid' : templateid},
        success: function(data)
        {
            if (data.success == "true")
            {
                json_data = JSON.parse(data.bracket_game_data);

                $("div#bracket_seeded_async").attr('data-bracket', JSON.stringify(json_data.bracket_data));
                $("div#bracket_seeded_async").attr('data-game-links', JSON.stringify(json_data.game_links));

                // we have async bracket data, draw the seeded tournament
                var bracket_data = $('div#bracket_seeded_async').attr('data-bracket');
                try
                {
                    bracket_data = JSON.parse(bracket_data);
                }
                catch (e)
                {
                    console.log(e);
                }

                $("#games-tab").click(function()
                {
                   setTimeout(function () {
                       $('div#bracket_seeded_async').bracket({
                           init: bracket_data /* data to initialize the bracket with */,
                           skipConsolationRound : true,
                           centerConnectors: true,
                           teamWidth: 150,
                           onMatchClick: onclick_seeded_match});
                   }, 100);
                });

                $("#games-tab").trigger('click');
            }
        }
    });
}

$(function () {

    $("#form_status").hide();
    $("#league_editing_window_status").hide();

    numberOfTeamsChanged();

    $("#tournament_status").modal('hide');
    $("#submit_create_new_tourney").click(function () {
        var old_text_value = jQuery(this).html();

        $('#submit_create_new_tourney').prop('disabled', true);
        $('#submit_create_new_tourney').html('<i class="fa fa-spinner fa-spin"></i> Creating Tournament...');

        var data = $('#create_tourney_form').serialize();

        var token = $("#create_tourney_form input[name=csrfmiddlewaretoken]").val();
        var fullData = null;
        $.ajax({
            type:"POST",
            beforeSend: function(request) {
                request.setRequestHeader("X-CSRFToken", token);
            },
            url:"/tournaments/submit/",
            data: data,
            success: function(data)
            {
               if (data.success == "true")
               {
                  // redirect to the tournament page
                  window.location = data.redirect_url;
               }
               else
               {
                   $("#form_status_text").text(data.errors.error);
                   $("#form_status").show();

                   $('#submit_create_new_tourney').html(old_text_value);
                   $('#submit_create_new_tourney').prop('disabled', false);
               }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                $("#form_status_text").text("There was a problem creating the tournament. Please try again.");
                $("#form_status").show();
            },
        }).always(function()
            {
                $('#submit_create_new_tourney').html(old_text_value);
                $('#submit_create_new_tourney').prop('disabled', false);
            }).fail(function()
            {
                $('#submit_create_new_tourney').html(old_text_value);
                $('#submit_create_new_tourney').prop('disabled', false);
            });
    });

    $("#form_status_close").click(function () {
        $("#form_status").hide();
    });

    hook_clan_league_buttons();
    hook_pr_buttons();
    hook_invite_players();
    hook_player_status_change();

    $("#create-division").on('click', function ()
    {
        update_division("add", jQuery(this));
    });

    $("#create-cl-template").on('click', function()
    {
        update_cl_templates("add", jQuery(this));
    });


    // hook up all the decline/join buttons to do the right things
    $(document).on('click', 'button[id^=join]', function() {
        handle_player_status_change(jQuery(this), true);
    });

    // handle and setup the decline button request/code
    $(document).on('click', 'button[id^=decline]', function() {
        handle_player_status_change(jQuery(this), false);
    });

    // hook up all the decline/join buttons to do the right things
    $(document).on('click', 'a[id^=cl-template-start-]', function() {
        var tournamentid = $("#tournamentid").val();
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        thisVar.prop('disabled', true);
        thisVar.html('<i class="fa fa-spinner fa-spin"></i> Starting Tournament...');
        var templateid = thisVar.data('template');
        $("#template_start_error").text('');
        $.ajax({
                type:"POST",
                url:"/cl/templates/start/",
                headers: {'X-CSRFToken': Cookies.get('csrftoken')},
                data: {'tournamentid' : tournamentid, 'templateid' : templateid},
                success: function(data)
                {
                   if (data.success == "true")
                   {
                      // update the table, which should have been returned to us

                      $("#templates").html(data.template_data);
                   }
                   else
                   {
                      // display the modal with the error
                       $("#template_start_error").text(data.error);
                   }
                },
                error: function(jqXHR, textStatus, errorThrown)
                {
                    // display the modal error form
                    thisVar.prop('disabled', false);
                    thisVar.html(old_text_value);
                },
                }).always(function()
                {
                    thisVar.prop('disabled', false);
                    thisVar.html(old_text_value);
                }).fail(function()
                {
                thisVar.html(old_text_value);
                thisVar.prop('disabled', false);
            });
        });

    $("#refresh_tournament").click(function() {
        var tournamentid = $("#tournamentid").val();
        var templateid = $("#templateid").val();
        var thisVar = jQuery(this);
        var old_text_value = thisVar.text();

        thisVar.prop('disabled', true);
        thisVar.html('<i class="fa fa-spinner fa-spin"></i> Refreshing Tournament...');

        var join = true;

          $.ajax({
                type:"POST",
                url:"/tournaments/refresh/",
                headers: {'X-CSRFToken': Cookies.get('csrftoken')},
                data: {'tournamentid' : tournamentid, 'templateid' : templateid},
                success: function(data)
                {
                   if (data.success == "true")
                   {
                        // update the table, which should have been returned to us
                        $("#lobbytab").html(data.team_table);
                        hook_player_status_change();

                        if ($("div#bracket_seeded_async").length)
                        {
                          refresh_tournament_async();
                        }
                        else
                        {
                            $("#gamestab").html(data.bracket_game_data);
                        }

                        if (data.can_start_tourney)
                        {
                            // We can now start the tournament, make sure the start button is enabled
                            $("#start_tournament").prop('disabled', false);
                        }
                        else
                        {
                            $("#start_tournament").prop('disabled', true);
                        }

                        if ($("div#gamelogtab-inner").length)
                        {
                           $("#gamelogtab-inner").html(data.game_log);
                           $('#game_log_data_table').DataTable();
                        }
                   }
                   else
                   {
                      // display the modal with the error
                      $("#tournament_status_title").text("Tournament Error");
                      $("#tournament_status_text").text(data.error);
                      $("#tournament_status").modal("show");
                   }
                },
                error: function(jqXHR, textStatus, errorThrown)
                {
                    // display the modal error form
                    thisVar.prop('disabled', false);
                    thisVar.html(old_text_value);
                },
            }).always(function()
                {
                    thisVar.prop('disabled', false);
                    thisVar.html(old_text_value);
                }).fail(function()
                {
                    thisVar.html(old_text_value);
                    thisVar.prop('disabled', false);
                });
    });


    // handle and setup the decline button request/code
    $(document).on('click', '#start_tournament', function() {
        var tournamentid = $("#tournamentid").val();
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        thisVar.prop('disabled', true);
        thisVar.html('<i class="fa fa-spinner fa-spin"></i> Starting Tournament...');

      $.ajax({
            type:"POST",
            url:"/tournaments/start_request/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'tournamentid' : tournamentid},
            success: function(data)
            {
               if (data.success == "true")
               {
                  // The tournament is now locked due to the host wanting
                  // to start it, to either move players to groups or to
                  // change seeds
                  $("#tournament_start_request_text").html(data.tournament_start_data);
                  $("#tournament_start_request_title").text("Tournament Start Request");
                  // make the nestable list active
                  $("#tournament_start_request_modal").modal('show');
                  $('#seed_list').nestable();
               }
               else
               {
                  // display the modal with the error
                  $("#tournament_start_request_title").text("Tournament Error");
                  $("#tournament_start_request_text").text(data.error);
                  $("#tournament_start_request").modal("show");
               }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                // display the modal error form
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            },
        }).always(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            }).fail(function()
            {
                thisVar.html(old_text_value);
                thisVar.prop('disabled', false);
            });
    });

     // handle and setup the decline button request/code
    $(document).on('click', 'button[id^=cl-update-player-]', function() {
        var tournamentid = $("#tournamentid").val();
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        thisVar.prop('disabled', true);
        thisVar.html('<i class="fa fa-spinner fa-spin"></i>');

        // no need to parse the id, we can do that on the backend, just send the data over
        var id = thisVar.attr('id');
        var data_attribs = thisVar.data();
        $("#tournament_invites_error_text").text("");
      $.ajax({
            type:"POST",
            url:"/tournaments/invite_players/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'tournamentid' : tournamentid, 'data_attrib': data_attribs, 'cl-update-player': 'true'},
            success: function(data)
            {
               if (data.success == "true")
               {
                  // update the division card table data
                  $('#' + data.division_div).html(data.division_card);
                  hook_invite_players();
                  hook_pr_buttons();
                  $("#tournament_invites").modal('hide');
                  if (data.can_start_tourney)
                  {
                      // We can now start the tournament, make sure the start button is enabled
                      $("#start_tournament").prop('disabled', false);
                  }
                  else
                  {
                      $("#start_tournament").prop('disabled', true);
                  }
               }
               else
               {
                  $("#tournament_invites_error_text").text(data.error);
               }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                // display the modal error form
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            },
        }).always(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            }).fail(function()
            {
                thisVar.html(old_text_value);
                thisVar.prop('disabled', false);
            });
    });

    // handle and setup the decline button request/code
    $(document).on('click', 'button[id^=invite-]', function() {
        var tournamentid = $("#tournamentid").val();
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        thisVar.prop('disabled', true);
        thisVar.html('<i class="fa fa-spinner fa-spin"></i> Inviting Player');

        // no need to parse the id, we can do that on the backend, just send the data over
        var id = thisVar.attr('id');

      $.ajax({
            type:"POST",
            url:"/tournaments/invite_players/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'tournamentid' : tournamentid, 'buttonid': id},
            success: function(data)
            {
               if (data.success == "true")
               {
                  // update the invited players and the inverse invited players (everyone not invited)
                  $("#invitetab").html(data.invited_players);
                  $("#tournament_invites_text").html(data.invited_players_inverse);
                  $("#tournament_invites").modal('show');
               }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                // display the modal error form
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            },
        }).always(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            }).fail(function()
            {
                thisVar.html(old_text_value);
                thisVar.prop('disabled', false);
            });
    });

    $('#league_editing_window').on('hidden.bs.modal', function () {
        $(this).modal('hide');
        $('.modal-backdrop').remove();
    });

    $('#tournament_start_request_modal').on('hidden.bs.modal', function () {
        var tournamentid = $("#tournamentid").val();

      $.ajax({
            type:"POST",
            url:"/tournaments/cancel_request/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'tournamentid' : tournamentid},
            success: function(data)
            {
               if (data.success != "true")
               {
                  // we should never get here
                  window.location = '/index/';
               }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
            },
        }).always(function()
            {
            }).fail(function()
            {
            });
    });

    $('#league_editing_window_submit').on('click', function () {
        var tournamentid = $("#tournamentid").val();
        var tournament_data = "";
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        jQuery(this).prop('disabled', true);
        jQuery(this).html('<i class="fa fa-spinner fa-spin"></i> Updating League Info....');

        // now grab the data from the window. since this is supposed to be arbitrary
        // per league type, let's just grab input values and pass to the corresponding
        // league on the back-end, each object will know how to use the data
        league_data = {}
        var actualRowIndex = 1;
        $('#league-editing-data-table tr').each(function (rowIndex, tr) {
            // for each row, send the data over in a format that's generic
            row_data = {}
            if (rowIndex == 0)
            {
                return true;
            }

            $('td', this).each(function (cellIndex, td) {
                var value = $(this).find(":input").val();
                var json_obj = {};
                if ($(this).find(":input").length)
                {
                    var id = $(this).find(":input").attr('id');
                    row_data[id + ""] = value;
                }
                else
                {
                    // there's no input, just and id/text...but send that over
                    var value = $(this).html();
                    var id = $(this).attr('id');
                    row_data[id + ""] = value;
                }
             });
             if (Object.keys(actualRowIndex + "").length > 0)
             {
                league_data[actualRowIndex + ""] = row_data;
             }
             actualRowIndex += 1;
        });

        league_data_json = JSON.stringify(league_data);
        $.ajax({
            type:"POST",
            url:"/leagues/submit_editing_window/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'leagueid' : tournamentid, 'league_editing_data' : league_data_json},
            success: function(data)
            {
               if (data.success == "true")
               {
                  $("#league_editing_window_status").removeClass('alert-danger');
                  $("#league_editing_window_status").addClass('alert-success');
               }
               else
               {
                  $("#league_editing_window_status").removeClass('alert-success');
                  $("#league_editing_window_status").addClass('alert-danger');
               }

               // add the editor data to the div
               $("#league_editing_window_title").text("League Editor");
               $("#league_editing_window_text").html(data.league_editor);
               $("#league_editing_window_status_text").html(data.editing_window_status_text);
               $("#league_editing_window_status").hide();
               $("#league_editing_window_status").show();
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            },
        }).always(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            }).fail(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            });
    });

    $('#tournament_start_request').on('click', function () {
        var tournamentid = $("#tournamentid").val();
        var tournament_data = "";
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        var seed_list = [];
        var team_list = [];
        // in order for the server logic to be easy let's parse the tables into
        // a semicolon delimited list of seeds/players
        $('#seed_ordered_list li').each(function (i, li) {
            seed_list.push(li.dataset.id);
            team_list.push(li.firstChild.id);
        });

        $('#group_ordered_list li').each(function (i, li) {
            seed_list.push(li.dataset.id);
            team_list.push(li.firstChild.id);
        });

        for (var i = 0; i < seed_list.length; i++)
        {
            if (i == 0)
            {
                tournament_data += seed_list[i] + "." + team_list[i];
            }
            else
            {
                tournament_data += ";" + seed_list[i] + "." + team_list[i];
            }
        }

        jQuery(this).prop('disabled', true);
        jQuery(this).html('<i class="fa fa-spinner fa-spin"></i> Starting Tournament....');

      $.ajax({
            type:"POST",
            url:"/tournaments/start/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'tournamentid' : tournamentid, 'tournament_data' : tournament_data},
            success: function(data)
            {
                if (data.success == "true")
                {
                    // redirect to the tournament page
                    window.location = data.redirect_url;
                }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            },
        }).always(function()
            {
            }).fail(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            });
    });

    // handle and setup the decline button request/code
    $(document).on('click', '#delete_tournament', function() {
        var tournamentid = $("#tournamentid").val();
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        thisVar.prop('disabled', true);
        thisVar.html('<i class="fa fa-spinner fa-spin"></i> Deleting Tournament...');

        var txt;
        var r = confirm("Are you sure you want to delete this? This action cannot be undone.");
        if (r != true)
        {
            thisVar.prop('disabled', false);
            thisVar.html(old_text_value);
            return;
        }

      $.ajax({
            type:"POST",
            url:"/tournaments/delete/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'tournamentid' : tournamentid},
            success: function(data)
            {
               if (data.success == "true")
               {
                  // update the table, which should have been returned to us
                  window.location = '/index/';
               }
               else
               {
                  // display the modal with the error
                  $("#tournament_status_title").text("Tournament Error");
                  $("#tournament_status_text").text(data.error);
                  $("#tournament_status").modal("show");
               }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                // display the modal error form
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            },
        }).always(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            }).fail(function()
            {
                thisVar.html(old_text_value);
                thisVar.prop('disabled', false);
            });
    });

    // handle and setup the decline button request/code
    $(document).on('click', '#league_editor', function() {
        var leagueid = $("#tournamentid").val();
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        thisVar.prop('disabled', true);
        thisVar.html('<i class="fa fa-spinner fa-spin"></i> Opening Editor...');

      $.ajax({
            type:"POST",
            url:"/leagues/league_editor/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'leagueid' : leagueid},
            success: function(data)
            {
               if (data.success == "true")
               {
                  // add the editor data to the div
                  $("#league_editing_window_title").text("League Editor");
                  $("#league_editing_window_text").html(data.league_editor);
                  $("#league_editing_window").modal("show");
               }
               else
               {
                  // display the modal with the error
                  $("#tournament_status_title").text("League Edit Error");
                  $("#tournament_status_text").text(data.error);
                  $("#tournament_status").modal("show");
               }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                // display the modal error form
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            },
        }).always(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            }).fail(function()
            {
                thisVar.html(old_text_value);
                thisVar.prop('disabled', false);
            });
    });

    // If there is async data that needs to be processed, check for those data types here
    if ($('div#bracket_seeded_async').length)
    {
        // We need to load the bracket data from the server
        refresh_tournament_async();
    }

    update_pause_resume_bindings();
});

function update_pause_resume_bindings()
{
    $('#pause').on('click', function () {
        var tournamentid = $("#tournamentid").val();
        var tournament_data = "";
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        jQuery(this).prop('disabled', true);
        jQuery(this).html('<i class="fa fa-spinner fa-spin"></i> Pausing league....');

       $.ajax({
            type:"POST",
            url:"/leagues/update_status/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'leagueid' : tournamentid, 'pause' : '1'},
            success: function(data)
            {
                if (data.success == "true")
                {
                    $('#pause_resume_buttons').html(data.pause_resume_buttons);
                    update_pause_resume_bindings();
                }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            },
        }).always(function()
            {
            }).fail(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            });
    });

    $('#resume').on('click', function () {
        var tournamentid = $("#tournamentid").val();
        var tournament_data = "";
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        jQuery(this).prop('disabled', true);
        jQuery(this).html('<i class="fa fa-spinner fa-spin"></i> Resuming league....');

       $.ajax({
            type:"POST",
            url:"/leagues/update_status/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'leagueid' : tournamentid, 'resume' : '1'},
            success: function(data)
            {
                if (data.success == "true")
                {
                    $('#pause_resume_buttons').html(data.pause_resume_buttons);
                    update_pause_resume_bindings();
                }
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            },
        }).always(function()
            {
            }).fail(function()
            {
                thisVar.prop('disabled', false);
                thisVar.html(old_text_value);
            });
    });

    $('#max_games').on('change', function () {
        var tournamentid = $("#tournamentid").val();
        var tournament_data = "";
        var old_text_value = jQuery(this).text();
        var thisVar = jQuery(this);

        var max_games = thisVar.find(':selected').data('games');
        var team_id = thisVar.find(':selected').data('team');
        jQuery(this).prop('disabled', true);

       $.ajax({
            type:"POST",
            url:"/max_games_at_once/",
            headers: {'X-CSRFToken': Cookies.get('csrftoken')},
            data: {'leagueid' : tournamentid, 'max_games' : max_games, 'team_id' : team_id },
            success: function(data)
            {
                thisVar.prop('disabled', false);
            },
            error: function(jqXHR, textStatus, errorThrown)
            {
                thisVar.prop('disabled', false);
            },
        }).always(function()
            {
            }).fail(function()
            {
                thisVar.prop('disabled', false);
            });
    });

    // DOCUMENTREADY
    $(".time_to_game").each(function ()
    {
        handle_game_countdown(jQuery(this));
    });

    $("#refresh_tournament").trigger('click');
    $('#game_log_data_table').DataTable();

    $("#tournament-filter").on("keyup", function() {
        handle_tournament_filter($(this));
    });

    $("#tournament-filter").on("onfocus", function() {
        handle_tournament_filter($(this));
    });

    $('div[data-role="tournament"]').each(function() {
        var text = $(this).find('input[data-role="finished-text"]').val();
        //console.log("Finished Text: " + text);
        if (text == "True")
        {
            $(this).hide();
        }
    });

    $("#finished-filter").on("click", function() {
        if ($("#finished-filter").is(':checked'))
        {
            // Show all tournament divs
            $('div[data-role="tournament"]').filter(function() {
                $(this).show();
            });
        }
        else
        {
            $('div[data-role="tournament"]').each(function() {
                var text = $(this).find('input[data-role="finished-text"]').val();
                if (text == "True")
                {
                    $(this).hide();
                }
            });
        }
    });
}

function handle_rtl_updates()
{
    // refresh everything
    $("#refresh_tournament").trigger('click');
    $('#game_log_data_table').DataTable();
}

function passive_toggle_item(obj, found, showFinished)
{
    var name = obj.find('span[data-role="filter-text"]').html();
    var finished = obj.find('input[data-role="finished-text"]').val() == "True";
    if (obj.is(":visible") && !found)
    {
        //console.log("Name: " + name + " Found:" + found + " Finished: " + finished + " show finished?" + showFinished + " action:hide");
        obj.hide();
    }
    else if (obj.is(":hidden") && found)
    {
        if (finished && !showFinished)
        {
            return;
        }
        //console.log("Name: " + name + " Found:" + found + " Finished: " + finished + " show finished?" + showFinished + " action:show");
        obj.show();
    }
}

function handle_tournament_filter(obj)
{
    var value = obj.val().toLowerCase();
    $('div[data-role="tournament"]').each(function() {
        var showFinished = $("#finished-filter").is(':checked');
        var found = false;
        $(this).find('span[data-role="filter-text"]').each(function() {
            var text = $(this).html().toLowerCase();
            var indexOf = text.indexOf(value);
            if ((text.length > 0) && (indexOf > -1))
            {
                //console.log("Text: "+text+" indexOf:"+indexOf);
                found = true;
            }
        });
        if (value.length == 0)
        {
            found = true;
        }
        passive_toggle_item($(this), found, showFinished);
    });
}

function toggle_div(divId)
{
    $("#" + divId).toggle();
}

var lastCheckedTemplate = 0;
function getTemplateSettings()
{
    var currentTemplateId = 0;
    if ($.isNumeric($('#templateid').val()))
    {
        currentTemplateId = $('#templateid').val();
        if (currentTemplateId != lastCheckedTemplate)
        {
            // Check the template
            // post something to /template_check/ to get the game settings back, and show that pane on the form
            $('#templatestatus').html('<i class="fa fa-spinner fa-spin"></i> Getting Template Settings');
            $.ajax({
                 type:"POST",
                 headers: {'X-CSRFToken': Cookies.get('csrftoken')},
                 url:"/tournaments/template_check/",
                 data: {
                        'templateid': $('#templateid').val() // from form
                        },
                 success: function(data)
                 {
                    if (data.success == 'true')
                    {
                        $('#templatestatus').text("Got settings for template: " + currentTemplateId);
                        // success
                        lastCheckedTemplate = currentTemplateId;

                        var templateSettings = JSON.stringify(data.settings);

                        // now update the screen read-only fields with the important pieces of the template settings
                        var paceString = data.Pace + ", DirectBoot: " + data.directBoot + " AutoBoot: " + data.autoBoot;
                        $('#templatepace').text(paceString);
                        $('#templatesettings').val(templateSettings);
                    }
                    else
                    {
                        // print the error on the screen
                        $('#templatestatus').text(data.error);
                    }
                 },
                 error: function(jqXHR, textStatus, errorThrown)
                 {
                    $('#templatestatus').text("There was a problem getting the template settings. Please try again");
                 }
            });
        }
    }
}

function getTournamentType()
{
    return $('#type').val();
}

function calculateRounds(numberOfTeams)
{
    // find the closest power of 2, starting at 2
    var rounds = Math.ceil(Math.log(numberOfTeams) / Math.log(2));

    // We've broken the loop, and i holds the true correct value
    return rounds;
}

function calculateGroupStageSeededTotal(numberOfTeams)
{
    return (numberOfTeams / 2);
}

function calculateGroupStageGroups(numberOfTeams)
{
    return numberOfTeams / 4;
}

function roundToNearestPowerOf2(numberOfTeams)
{
    numberOfTeams = Math.pow(2, calculateRounds(numberOfTeams));

    return numberOfTeams;
}

// Number of teams influences max players + rounds
function numberOfTeamsChanged()
{
    var type = getTournamentType();
    var playersPerTeam = $('#players_team').val();
    var numberOfTeams = $('#number_teams').val();
    numberOfTeams = roundToNearestPowerOf2(numberOfTeams);

    switch (type)
    {
        case "1": // group stage tournaments
        {
            var rounds = calculateGroupStageGroups(numberOfTeams);
            $("#rounds_text").text(rounds);
            $("#rounds").val(rounds);

            var knockoutTeams = calculateGroupStageSeededTotal(numberOfTeams);
            $("#knockout_teams_text").text(knockoutTeams);
            $("#knockout_teams").val(knockoutTeams);

            var maxPlayers = numberOfTeams * playersPerTeam;
            $('#number_players_text').text(maxPlayers);
            $('#number_players').val(maxPlayers);
            break;
        }

        case "2": // swiss tournaments
        {
            // number of teams have changed, update max players and rounds
            var rounds = calculateRounds(numberOfTeams);

            $('#rounds_text').text(rounds);
            $('#rounds').val(rounds);

            var maxPlayers = numberOfTeams * playersPerTeam;
            $('#number_players_text').text(maxPlayers);
            $('#number_players').val(maxPlayers);
            break;
        }

        case "3": // seeded tournaments
        {
            var rounds = calculateRounds(numberOfTeams);

            $('#rounds_text').text(rounds);
            $('#rounds').val(rounds);

            var maxPlayers = numberOfTeams * playersPerTeam;
            $('#number_players_text').text(maxPlayers);
            $('#number_players').val(maxPlayers);

            $('#number_teams_text').text(numberOfTeams);
            $('#number_teams').val(numberOfTeams);

            break;
        }

        case "4": // random team tournaments
        {
            var rounds = numberOfTeams - 1;
            $('#rounds_text').text(rounds);
            $('#rounds').val(rounds);

            var maxPlayers = numberOfTeams * playersPerTeam;
            $('#number_players_text').text(maxPlayers);
            $('#number_players').val(maxPlayers);

            $('#number_teams_text').text(numberOfTeams);
            $('#number_teams').val(numberOfTeams);
        }
    }

    // regardless, there are even teams in every tournament
    $('#number_teams_text').text(numberOfTeams);
    $('#number_teams').val(numberOfTeams);
}

// Players per teams only influences the max players in the tournament
function playersPerTeamChanged()
{
    var type = getTournamentType();

    var playersPerTeam = $('#players_team').val();
    var numberOfTeams = $('#number_teams').val();

    var maxPlayers = $('#number_teams').val() * playersPerTeam;
    $('#number_players').val(maxPlayers);
    $('#number_players_text').text(maxPlayers);

    $('#players_team_text').text(playersPerTeam);

    switch (type)
    {
        case "1": // group stage tournaments
        {
            break;
        }

        case "2": // swiss tournaments
        {
            // We've got the new amount of round
            break;
        }

        case "3": // seeded tournaments
        {
            break;
        }
    }
}