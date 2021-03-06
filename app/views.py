import os, random, json, requests, urllib, urlparse
from django.shortcuts import render
from django.http import HttpResponse
from urllib2 import Request, urlopen, URLError
from .models import Greeting, Game, Player

color_emoji_map = {"R": ":red_circle:", "B": ":large_blue_circle:", "X": ":black_circle:", "":":white_circle:"}

# Create your views here.
def index(request):
    return render(request, 'index.html')

def test_webhook(request):
    req_dict = urlparse.parse_qs(urllib.unquote(request.body))
    print(req_dict)
    return HttpResponse(json.dumps({"text": "That seems to have done something! I'm not sure what..." }), content_type='application/json')


def db(request):
    greeting = Greeting()
    greeting.save()

    greetings = Greeting.objects.all()

    return render(request, 'db.html', {'greetings': greetings})

def initialize_game(request):
    # create a game instance in the db then let the users pick teams
    req_dict = urlparse.parse_qs(urllib.unquote(request.body))
    user_id = req_dict['user_id'][0]
    user_name = req_dict['user_name'][0]
    channel_id = req_dict['channel_id'][0]

    # if there's already an active game in the channel, respond with error
    if Game.objects.filter(channel_id=channel_id).count() > 0:
        payload = {"response_type": "ephemeral", "replace_original": False, "text": "There's already a game in progress!"}
    else:
        # create a new game in channel with the generated data
        game_board_data = generate_wordset()
        Game.objects.create(
            map_card = json.dumps(game_board_data["map_card"]),
            word_set = json.dumps(game_board_data["words_list"]),
            current_team_playing = game_board_data["starting_team"],
            channel_id = channel_id,
            game_master = user_id
        )
        payload={
                "text": "<@{}> wants to play a game of Codenames".format(user_id, user_name),
                "response_type": "in_channel",
                "attachments": [
                    {
                        "text": "Choose a team",
                        "fallback": "You are unable to choose a game",
                        "callback_id": "team_chosen",
                        "color": "#3AA3E3",
                        "attachment_type": "default",
                        "actions": [
                            {
                                "name": "blue",
                                "text": ":large_blue_circle: Blue Team",
                                "type": "button",
                                "value": "blue",
                            },
                            {
                                "name": "red",
                                "text": ":red_circle: Red Team",
                                "type": "button",
                                "value": "red",
                            }
                        ]
                    }
                ]
            }
    return HttpResponse(json.dumps(payload), content_type='application/json')

def close_teams(request):
    req_dict = urlparse.parse_qs(urllib.unquote(request.body))
    user_name = req_dict['user_name'][0]
    user_id = req_dict['user_id'][0]
    channel_id = req_dict['channel_id'][0]

    if Player.objects.filter(game__channel_id=channel_id).count() < 4:
        return HttpResponse({"text": "There needs to be at least 4 players for a game."}, content_type='application/json')

    # disable team selection, and let users pick their team captains
    if Game.objects.filter(channel_id=channel_id).count == 0:
        payload = {"text": "There's no active game in the channel, try `/codenames`."}
    else:
        active_game_in_channel = Game.objects.get(channel_id=channel_id)
        if active_game_in_channel.accepting_new_players == False:
            return HttpResponse({"text": "Teams are closed for the current game."}, content_type='application/json')
        if user_id != active_game_in_channel.game_master:
            payload = {"text": "Only the game master (<@{}>) can finalize the teams.".format(active_game_in_channel.game_master)}
        else:
            active_game_in_channel.accepting_new_players = False
            # show buttons to pick team leaders
            actions = []
            for blue_player in Player.objects.filter(team_color='blue', game_id=active_game_in_channel.id):
                actions.append({
                    "name": "blue_spymaster",
                    "text": blue_player.username,
                    "type": "button",
                    "value": blue_player.slack_id
                })
            payload = {
                "text": "<@{}>, choose a Spymaster (clue-giver) for the *Blue* team.".format(active_game_in_channel.game_master),
                "response_type": "in_channel",
                "attachments": [
                    {
                        "fallback": "unable to choose spymaster",
                        "callback_id": "spymaster_chosen",
                        "color": "#3AA3E3",
                        "attachment_type": "default",
                        "actions": actions
                    }
                ]
            }

    return HttpResponse({json.dumps(payload)}, content_type='application/json')

def generate_wordset():
    # read the words_list file and build an array of words
    words = []
    words_file = open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'words_list.txt'))
    for line in words_file:
        words.append(line.strip())
    total_num_words = len(words)

    # get 25 unique words at random from the list of words
    words_list = [words[idx] for idx in random.sample(range(0, total_num_words -1), 25)]
    starting_team = ["red", "blue"][random.randint(0,1)]
    map_card = generate_mapcard(starting_team)
    staring_team = determine_starting_team(map_card)

    data = {"words_list": words_list, "map_card": map_card, "starting_team": starting_team}

    return data

def determine_starting_team(map_card):
        r_count = 0
        b_count = 0
        for card in map_card:
            if card == "R":
                r_count += 1
            elif card == "B":
                b_count += 1
        if r_count > b_count:
            return "red"
        else:
            return "blue"

def generate_mapcard(starting_team):
    num_red_agents = 8
    num_blue_agents = 8

    # double agent
    if starting_team == "red":
        num_red_agents += 1
    else:
        num_blue_agents += 1

    ret = [""] * 25
    # generate 17 random indices (8 + 9 agents) for the 25 cards
    indices = random.sample(range(0, 24), 18)
    red_card_indices = indices[0: num_red_agents]
    blue_card_indices = indices[num_red_agents: 17]

    for red_idx in red_card_indices:
        ret[red_idx] = "R"
    for blue_idx in blue_card_indices:
        ret[blue_idx] = "B"

    #assassin card
    ret[indices[17]] = "X"

    return ret

def cancel_game(request):
    try:
        req_dict = urlparse.parse_qs(urllib.unquote(request.body))
        channel_id = req_dict['channel_id'][0]
        user_id = req_dict['user_id'][0]

        current_game = Game.objects.get(channel_id=channel_id)
        Player.objects.filter(game_id=current_game.id).delete()
        Game.objects.filter(channel_id=channel_id).delete()
        payload =  {
                "text": "Successfully deleted all game data!",
                "response_type": "in_channel",
            }
    except Game.DoesNotExist:
        payload = {
                "text": "No game exists. To start one, try `/codenames`",
                "response_type": "in_channel",
            }

    return HttpResponse(json.dumps(payload), content_type='application/json')


def show_map_card(request):
    # restricted to users who are flagged as spymasters for the game
    req_dict = urlparse.parse_qs(urllib.unquote(request.body))
    channel_id = req_dict['channel_id'][0]
    user_id = req_dict['user_id'][0]

    if Game.objects.filter(channel_id=channel_id).count() == 0:
        payload = {'text': "There is no active game in this channel, try `/codenames`"}
    else:
        active_game = Game.objects.get(channel_id=channel_id)
        if Player.objects.filter(slack_id=user_id, game_id=active_game.id).count() == 0:
            payload = {'text': "You aren't currently in a game of Codenames."}
        elif Player.objects.get(slack_id=user_id, game_id=active_game.id).is_spymaster == False:
            payload = {'text': "You aren't flagged as a spymaster for the current game."}
        else:
            payload = generate_map_card(active_game)

    return HttpResponse(json.dumps(payload), content_type='application/json')

def button(request):
    # parse the request to a dict
    req_dict = json.loads(urlparse.parse_qs(urllib.unquote(request.body))['payload'][0])
    response_url = req_dict['response_url']
    actions = req_dict["actions"] #ex: [{u'name': u'chess', u'value': u'chess'}]
    callback_id = req_dict["callback_id"] #ex: wopr_game
    channel = req_dict["channel"] #ex: {u'id': u'C3NUEG0S0', u'name': u'game'}
    user = req_dict["user"] #ex: {u'id': u'U3N3Z66TB', u'name': u'dustin'}
    button_value = req_dict['actions'][0]['value']
    button_name = req_dict['actions'][0]['name']

    try:
        active_game_in_channel = Game.objects.get(channel_id=channel['id'])
    except Game.DoesNotExist:
        payload = {'text': "I don't think that game exists anymore...sorry!", "replace_original": False}
        return HttpResponse(json.dumps(payload), content_type='application/json')

    # detect if the user is picking a team
    if button_name == "blue" or button_name == "red":
        payload = handle_team_selection(active_game_in_channel, channel, user, button_value)
    elif button_name == "blue_spymaster":
        payload = handle_blue_spymaster_selection(active_game_in_channel, channel, user, button_value)
    elif button_name == "red_spymaster":
        payload = handle_red_spymaster_selection(active_game_in_channel, channel, user, button_value)
    elif button_name == "card":
        payload = user_select_button_with_text(active_game_in_channel, button_value, user['id'])
        if payload.get('attachments'):
            # if we're about to show a board...
            requests.post(response_url, data=json.dumps({'text':'<@{}> selected "{}"'.format(user['id'], button_value), 'replace_original': False, "response_type": "in_channel"}))
    elif button_name == "end":
        payload = user_did_end_turn(active_game_in_channel, user['id'], response_url)
    elif button_name == "map_reveal":
        payload = show_spymaster_map_card(active_game_in_channel, user['id'])
    else:
        payload = {'text': "That does nothing! But great job!", "replace_original": False}

    return HttpResponse(json.dumps(payload), content_type='application/json')

def show_spymaster_map_card(active_game, user_id):
    player_obj = Player.objects.get(slack_id=user_id, game_id=active_game.id)
    if player_obj.is_spymaster == False:
        payload = {'text': "You aren't flagged as a spymaster for the current game.", "replace_original": False}
    else:
        payload = generate_map_card(Game.objects.get(id=active_game.id))
    return payload

def generate_map_card(active_game):
    map_card = json.loads(active_game.map_card)
    word_set = json.loads(active_game.word_set)
    revealed_cards = json.loads(active_game.revealed_cards)
    attachments = []
    actions = []
    for (idx, color) in enumerate(map_card):
        if word_set[idx] in revealed_cards:
            word = "(revealed)"
        else:
            word = word_set[idx]
        btn_text = "{} {}".format(color_emoji_map[map_card[idx]], word)
        actions.append({
            "name": "map_card",
            "text": btn_text,
            "type": "button",
            "value": "map_card",
        })
    for x in range(1,6):
        attachments.append({
                "fallback": "error displaying mapcard",
                "callback_id": "red map_card shown",
                "color": "#3AA3E3",
                "attachment_type": "default",
                "actions": actions[(x-1)*5:x*5]
            })
    payload = {
        "text": "Here's the map card!",
        "attachments": attachments,
        "replace_original": False,
        "response_type": "ephemeral"
    }

    return payload

def user_select_button_with_text(active_game, button_text, user_id):
    # get the index of the card to be revealed
    player_obj = Player.objects.get(game_id=active_game.id, slack_id=user_id)
    if player_obj.is_spymaster == True:
        return {"replace_original": False, "text": "A spymaster can't pick cards."}
    if player_obj.team_color != active_game.current_team_playing:
        return {"replace_original": False, "text": "Please wait for the *{}* team to finish their turn.".format(active_game.current_team_playing)}
    if active_game.num_guesses_left == 0:
        return {"replace_original": False, "text": "Your spymaster, <@{}>, needs to give a hint first".format(
            Player.objects.get(game_id=active_game.id, is_spymaster=True, team_color=active_game.current_team_playing).slack_id
        )}

    word_set = json.loads(active_game.word_set)
    map_card = json.loads(active_game.map_card)
    blunderer = None
    winning_team = None

    map_card_to_team_color = {
        "R": "red",
        "B": "blue",
        "": "white",
        "X": "assassin"
    }
    selected_word_team_color = map_card_to_team_color[map_card[word_set.index(button_text)]]

    try:
        revealed_cards = json.loads(active_game.revealed_cards)
    except ValueError:
        revealed_cards = []

    revealed_cards.append(button_text)
    Game.objects.filter(id=active_game.id).update(revealed_cards=json.dumps(revealed_cards))
    active_game.revealed_cards = json.dumps(revealed_cards)

    ''' There are now three types of reponses a valid user can anticipate after clicking a button '''
    # 1) if the player picked the assassin it's an auto-lose for their team
    if selected_word_team_color == "assassin":
        #show the entire board + dialog that the game is over
        active_game.revealed_cards = active_game.word_set
        revealed_cards = json.loads(active_game.revealed_cards)
        if active_game.current_team_playing == "red":
            winning_team = "blue"
        else:
            winning_team = "red"
        blunderer = user_id
    # 2) the player picked correctly
    active_game_filter = Game.objects.filter(id=active_game.id)
    if player_obj.team_color == selected_word_team_color:
        active_game_filter.update(num_guesses_left = active_game.num_guesses_left - 1)
        active_game.num_guesses_left -= 1
        # if the team hit their total num cards, they won
        if did_team_win_game(active_game, None):
            # first determine if the team did win
            active_game.revealed_cards = active_game.word_set
            revealed_cards = json.loads(active_game.revealed_cards)
            if active_game.current_team_playing == "red":
                winning_team = "red"
            else:
                winning_team = "blue"

        if active_game.num_guesses_left == 0:
            # switch the teams if the num_guesses went to 0
            if active_game.current_team_playing == "blue":
                active_game.current_team = "red"
                active_game_filter.update(current_team_playing="red")
            else:
                active_game.current_team = "blue"
                active_game_filter.update(current_team_playing="blue")

    # 3) the player picked incorrectly (the other team's color or a neutral card)
    if player_obj.team_color != selected_word_team_color:
        active_game.num_guesses_left = 0
        active_game_filter.update(num_guesses_left=0)
        if active_game.current_team_playing == "blue":
            active_game.current_team="red"
            active_game_filter.update(current_team_playing="red")
        else:
            active_game.current_team="blue"
            active_game_filter.update(current_team_playing="blue")

        # in an edge case, the player can blunder the game by picking the wrong team's winning card
        # the game should then be over.
        if did_team_win_game(active_game, 'R'):
            winning_team = 'red'
        if did_team_win_game(active_game, 'B'):
            winning_team = 'blue'

        if winning_team:
            active_game.revealed_cards = active_game.word_set
            revealed_cards = json.loads(active_game.revealed_cards)
            blunderer = user_id

    payload = generate_current_board_state(active_game, revealed_cards, winning_team, blunderer)
    return payload

def generate_current_board_state(active_game, revealed_cards, winning_team=None, blunderer=None):
    active_game = Game.objects.get(id=active_game.id)
    attachments = []
    actions = []
    word_set = json.loads(active_game.word_set)
    map_card = json.loads(active_game.map_card)
    for (idx, word) in enumerate(word_set):
        button_color = map_card[idx]
        if word in revealed_cards:
            actions.append({
                "name": "card revealed",
                "text": "{} {}".format(color_emoji_map[button_color], word),
                "type": "button",
                "value": word

            })
        else:
            actions.append({
                "name": "card",
                "text": word,
                "type": "button",
                "value": word
            })

    for x in range (1, 6):
        attachments.append({
                "fallback": "error picking card",
                "callback_id": "card_chosen",
                "attachment_type": "default",
                "actions": actions[(x-1)*5:x*5]
            })
    if winning_team:
        payload = {
            "title": "Game Over",
            "text": "The *{}* team won!".format(winning_team),
            "attachments": attachments,
            "replace_original": False,
            "delete_original": True,
            "response_type": "in_channel"
        }
        if blunderer:
            payload["text"] = "<@{}> blundered it! The *{}* team won!".format(blunderer, winning_team)
    else:
        # remind the players of the teams
        players_in_game = Player.objects.filter(game_id=active_game.id)
        red_spymaster = players_in_game.get(is_spymaster=True, team_color='red')
        red_players = players_in_game.filter(is_spymaster=False, team_color='red')
        blue_spymaster = players_in_game.get(is_spymaster=True,team_color='blue')
        blue_players = players_in_game.filter(is_spymaster=False, team_color='blue')

        red_team = "<@{}>(:sunglasses:), ".format(red_spymaster.slack_id) + ', '.join(["<@{}>".format(player.slack_id) for player in red_players])
        blue_team = "<@{}>(:sunglasses:), ".format(blue_spymaster.slack_id) + ', '.join(["<@{}>".format(player.slack_id) for player in blue_players])

        attachments.append({
            "title": "As a reminder, here are the teams:",
            "text": ":red_circle:{} \n :large_blue_circle:{}".format(red_team, blue_team)
        })
        attachments.append({
            "fallback": "error ending turn",
            "callback_id":  "turn_ended",
            "attachment_type": "default",
            "actions": [
                {
                    "name": "end",
                    "text": ":x: End Turn",
                    "style": "danger",
                    "type": "button",
                    "value": "end",
                    "confirm": {
                        "title": "Are you sure?",
                        "text": "This will end your team's turn.",
                        "ok_text": "Yes",
                        "dismiss_text": "No"
                    }
                },
                {
                    "name": "map_reveal",
                    "text": ":world_map: Show Map Card",
                    "style": "primary",
                    "type": "button",
                    "value": "end"
                }
            ]
        })


        if active_game.num_guesses_left == 0:
            # ask the team's spymaster to specify a hint
            guess_message = "<@{}>, use */give_hint `word,` `num_guesses`* to give your team a hint.".format(
                Player.objects.get(is_spymaster=True, team_color=active_game.current_team_playing, game_id=active_game.id).slack_id
            )
        else:
            guess_message = "Guesses: *{}* _(+1)_".format(active_game.num_guesses_left - 1)
        current_team_emoji = get_emoji_from_current_team_playing(active_game)
        payload = {
            "title": "Here's the board!",
            "text": "Current Team Playing: {} \n {}".format(current_team_emoji, guess_message),
            "response_type": "in_channel",
            "attachments": attachments,
            "replace_original": False,
            "delete_original": True,
        }
    return payload

def handle_team_selection(active_game, channel, user, button_value):
    # prevent a player from adding themselves to the game multiple times
    if active_game.accepting_new_players == False:
        payload = {'text': "Teams for this channel's active game have been locked.", "replace_original": False}
    else:
        if Player.objects.filter(slack_id=user['id'], game=active_game).count() > 0:
            payload = {'text': "You've already been added to this game.", "replace_original": False}
        else:
            # create a to-be-deleted player object that fk's a player to the game instance
            Player.objects.create(
                slack_id=user['id'],
                username=user['name'],
                team_color=button_value,
                game=active_game
            )
            payload = {'text': "added <@{}> to the {} team.".format(user['name'], button_value), "replace_original": False, "response_type": "in_channel"}

    return payload

def handle_blue_spymaster_selection(active_game, channel, user, button_value):
    # assert the person who clicked the button is the spymaster
    if active_game.game_master != user['id']:
        payload = {"text": "Only the game master (<@{}>) can set a spymaster".format(active_game.game_master), "replace_original": False}
    else:
        Player.objects.filter(game__channel_id=channel['id'], slack_id=button_value).update(is_spymaster=True)
        actions = []
        for red_player in Player.objects.filter(team_color='red', game_id=active_game.id):
            actions.append({
                "name": "red_spymaster",
                "text": red_player.username,
                "type": "button",
                "value": red_player.slack_id
            })
        payload =  {
                "text": "<@{}> was set as the Blue spymaster, now choose the *Red* spymaster.".format(button_value),
                "response_type": "in_channel",
                "attachments": [
                    {
                        "fallback": "unable to choose spymaster",
                        "callback_id": "spymaster_chosen",
                        "color": "#3AA3E3",
                        "attachment_type": "default",
                        "actions": actions
                    }
                ]
            }
    return payload

def user_did_end_turn(active_game, user_id, response_url):
    # enforce the user who clicked this must be a spymaster of the current team
    player = Player.objects.get(slack_id=user_id, game=active_game)
    active_game_filter = Game.objects.filter(id=active_game.id)

    if active_game.current_team_playing != player.team_color:
        payload = {"replace_original": False, "text": "You can't end another team's turn"}
    elif player.is_spymaster == True:
        payload = {"replace_original": False, "text": "A spymaster can't end their team's turn."}
    else:
        active_game.num_guesses_left = 0
        active_game_filter.update(num_guesses_left=0)
        if active_game.current_team_playing == "blue":
            active_game.current_team="red"
            active_game_filter.update(current_team_playing="red")
        else:
            active_game.current_team="blue"
            active_game_filter.update(current_team_playing="blue")

        requests.post(response_url, data=json.dumps({'text':"<@{}> ended the {} team's turn.".format(user_id, active_game.current_team_playing), 'replace_original': False, "response_type": "in_channel"}))
        payload = generate_current_board_state(active_game, active_game.revealed_cards)

    return payload



def handle_red_spymaster_selection(active_game, channel, user, button_value):
    if active_game.game_master != user['id']:
        payload = {"text": "Only the game master (<@{}>) can set a spymaster".format(active_game.game_master), "replace_original": False}
    else:
        Player.objects.filter(game_id=active_game.id, slack_id=button_value).update(is_spymaster=True)
        # teams and spymasters have been chosen, show the board
        payload = generate_current_board_state(active_game, json.loads(active_game.revealed_cards))

    return payload

def get_emoji_from_current_team_playing(active_game):
    game = Game.objects.get(id=active_game.id)
    if game.current_team_playing == "red":
        return ":red_circle:"
    else:
        return ":large_blue_circle:"

def did_team_win_game(active_game, color):
    game = Game.objects.get(id=active_game.id)

    # override the color selection here if a color was provided as an argument
    if color:
        card_color = color
    elif game.current_team_playing == "red":
        card_color = "R"
    else:
        card_color = "B"

    map_card = json.loads(game.map_card) # an array of letters representing card color
    word_set = json.loads(game.word_set) # an array of random words
    target_cards = 0
    for card in map_card:
        if card == card_color:
            target_cards += 1

    actual_revealed_cards = 0
    for (idx, revealed_word) in enumerate(json.loads(game.revealed_cards)):
        idx_of_card = word_set.index(revealed_word)
        if map_card[idx_of_card] == card_color:
            actual_revealed_cards += 1

    print(target_cards)
    print(actual_revealed_cards)
    return target_cards == actual_revealed_cards

def give_hint(request):
    req_dict = urlparse.parse_qs(urllib.unquote(request.body))
    user_name = req_dict['user_name'][0]
    user_id = req_dict['user_id'][0]
    channel_id = req_dict['channel_id'][0]

    current_game = Game.objects.get(channel_id=channel_id)
    requesting_player = Player.objects.get(slack_id=user_id, game_id=current_game.id)
    current_team_playing = current_game.current_team_playing

    if requesting_player.team_color != current_team_playing:
        payload = {"replace_original": False, "text": "Please wait for the {} team to finish their turn.".format(current_team_playing)}
    elif requesting_player.is_spymaster == False:
        payload = {"replace_original": False, "text": "You aren't the spymaster for your team."}
    else:
        try:
            hint = req_dict['text'][0]
            formatted_hint = hint.split(",")
            word = formatted_hint[0]
            num_guesses = abs(int(formatted_hint[1]))
            # weird rule where users can select 1 more than the specified num guesses
            Game.objects.filter(channel_id=channel_id).update(num_guesses_left = num_guesses + 1)
            print("NUM GUESSES LEFT: {}".format(current_game.num_guesses_left))
            payload =  {
                    "text": "> <@{}>'s hint: *'{}'*, *{}*".format(user_id, word.strip().upper(), num_guesses),
                    "response_type": "in_channel",
                }
        except:
            payload = {"replace_original": False, "text": "Your hint was improperly formatted."}
    return HttpResponse(json.dumps(payload), content_type='application/json')
