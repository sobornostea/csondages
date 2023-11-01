import telebot
import traceback
import logging
import time
import json
import yaml
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO
import re
import traceback
import sys


class MyYAML(YAML):
    def dump(self, data, stream=None, **kw):
        inefficient = False
        if stream is None:
            inefficient = True
            stream = StringIO()
        YAML.dump(self, data, stream, **kw)
        if inefficient:
            return stream.getvalue()


def escape(htmlstring):
    # This is done first to prevent escaping other escapes.
    htmlstring = htmlstring.replace("&", "&amp;")
    htmlstring = htmlstring.replace("<", "&lt;")
    htmlstring = htmlstring.replace(">", "&gt;")
    return htmlstring


def jade(ev):
    #    if ev.from_user.username in ["pyxyne","sobornostea"]:
    #        bot.send_message(ev.chat.id, str(sys.exc_info()))
    pass


yaml = MyYAML()

# module constants
MEDIA_FILTER_TYPES = ("photo", "animation", "document", "video", "sticker")
CAPTIONABLE_TYPES = ("photo", "audio", "animation", "document", "video", "voice")
HIDE_FORWARD_FROM = set(
    [
        "anonymize_bot",
        "AnonFaceBot",
        "AnonymousForwarderBot",
        "anonomiserBot",
        "anonymous_forwarder_nashenasbot",
        "anonymous_forward_bot",
        "mirroring_bot",
        "anonymizbot",
        "ForwardsCoverBot",
        "anonymousmcjnbot",
        "MirroringBot",
        "anonymousforwarder_bot",
        "anonymousForwardBot",
        "anonymous_forwarder_bot",
        "anonymousforwardsbot",
        "HiddenlyBot",
        "ForwardCoveredBot",
        "anonym2bot",
        "AntiForwardedBot",
        "noforward_bot",
        "Anonymous_telegram_bot",
    ]
)
VENUE_PROPS = (
    "title",
    "address",
    "foursquare_id",
    "foursquare_type",
    "google_place_id",
    "google_place_type",
)

# module variables
bot = None
db = None
ch = None
message_queue = None
registered_commands = {}

# settings
allow_documents = None
linked_network: dict = None


def init(config):
    global bot, message_queue, allow_documents, linked_network
    if config["bot_token"] == "":
        logging.error("No telegram token specified.")
        exit(1)

    logging.getLogger("urllib3").setLevel(
        logging.INFO
    )  # very noisy with debug otherwise
    telebot.apihelper.READ_TIMEOUT = 20

    bot = telebot.TeleBot(config["bot_token"], threaded=False)

    types = ["poll", "text"]
    set_handler(relay, content_types=types)


def set_handler(func, *args, **kwargs):
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as e:
            logging.exception("Exception raised in event handler")

    bot.poll_handler(func=lambda ev: ev.content_type == "poll", *args, **kwargs)(
        wrapper
    )
    bot.message_handler(*args, **kwargs)(wrapper)
    bot.inline_handler(lambda m: True, *args, **kwargs)(wrapper)


def run():
    while True:
        try:
            bot.polling(none_stop=True, long_polling_timeout=45)
        except Exception as e:
            # you're not supposed to call .polling() more than once but I'm left with no choice
            logging.warning("%s while polling Telegram, retrying.", type(e).__name__)
            time.sleep(1)


def relay(ev):
    print(ev)
    if ev.content_type == "poll":
        serialize(ev)
    elif ev.content_type == "text":
        deserialize(ev)
    else:
        logging.info("Unknown command")


def poll_to_dict(poll):
    deserialized_options = []
    for options in poll.options:
        deserialized_options.append(options.text)
    deserialized_poll = {
        "question": poll.question,
        "options": deserialized_options,
        "is_anonymous": poll.is_anonymous,
        "type": poll.type,
        "allows_multiple_answers": poll.allows_multiple_answers,
        "correct_option_id": poll.correct_option_id,
        "explanation": poll.explanation,
        "open_period": poll.open_period,
        "close_date": poll.close_date,
    }
    return {k: v for k, v in deserialized_poll.items() if v is not None}


def serialize(ev):
    poll_dict = poll_to_dict(ev.poll)
    poll_text = ""
    poll_text = MyYAML().dump(poll_dict)
    formatted_poll_text = (
        '<pre><code class="language-yaml">' + escape(poll_text) + "</code></pre>"
    )
    logging.info(str(ev.from_user.username) + "\n " + poll_text)
    return bot.send_message(ev.chat.id, formatted_poll_text, parse_mode="HTML")


def deserialize(ev):
    logging.info(str(ev.from_user.username) + "\n " + ev.text)
    poll_dict = {}
    # Check only the first entity
    if "entities" in ev.json and ev.json["entities"][0]["type"] == "bot_command":
        if "/help" in ev.text:
            return bot.send_message(
                ev.chat.id,
                "Si tu veux m'utiliser, envoie moi le sondage que tu veux modifier. Je te renverrais un texte, dont tu modifieras les options, et que tu me renverras. Je t'enverrais un sondage que tu pourras forward !",
            )
        if "/redo" in ev.text:
            if ev.reply_to_message is not None:
                if ev.reply_to_message.content_type == "poll":
                    poll_dict = poll_to_dict(ev.reply_to_message.poll)
                    try:
                        return bot.send_poll(chat_id=ev.from_user.id, **poll_dict)
                    except Exception as e:
                        logging.error("Poll error")
                        return bot.send_message(
                            ev.chat.id, "Je ne suis pas arrivé à copier ce sondage"
                        )
            return bot.send_message(
                ev.chat.id,
                "Il faut répondre à un sondage pour utiliser cette commande !",
            )

    try:
        poll_dict = YAML(typ="safe").load(ev.text)
    except Exception:
        logging.error("Parser error")
        jade(ev)
        return bot.send_message(
            ev.chat.id,
            "Je n'ai pas compris le format. Si tu as mis des \":\", essaye de mettre des ' autour du champ (par exemple \n question: 'Je veux:' \nà la place de \n question: Je veux:",
        )

    if "correct_option_id" in poll_dict:
        poll_dict["type"] = "quiz"
    try:
        return bot.send_poll(chat_id=ev.from_user.id, **poll_dict)
    except Exception as e:
        logging.error("Poll error")
        jade(ev)
        return bot.send_message(
            ev.chat.id,
            "Si tu veux m'utiliser, envoie moi le sondage que tu veux modifier. Je te renverrais un texte, dont tu modifieras les options, et que tu me renverras. Je t'enverrais un sondage que tu pourras forward !",
        )
