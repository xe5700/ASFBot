#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os

os.chdir(os.path.dirname(os.path.realpath(__file__)))
import argparse
import re

import requests.exceptions
import telebot

import logger
from ASFConnector import ASFConnector

_REGEX_CDKEY = re.compile('\w{5}-\w{5}-\w{5}')
_REGEX_COMMAND_BOT_ARGS = '^[/!]\w+\s*(?P<bot>\w+)?\s+(?P<arg>.*)'
_REGEX_COMMAND_RAW = '^[/!](?P<input>(?P<command>\w+).*)'
_REGEX_COMMAND = '^[/!]\w+\s*(?P<bot>\w+)?'
_ENV_TELEGRAM_API_HOST = "TELEGRAM_API_HOST"
_ENV_TELEGRAM_BOT_TOKEN = "TELEGRAM_BOT_TOKEN"
_ENV_TELEGRAM_USER_ALIAS = "TELEGRAM_USER_ALIAS"
_ENV_ASF_IPC_HOST = "ASF_IPC_HOST"
_ENV_ASF_IPC_PORT = "ASF_IPC_PORT"
_ENV_ASF_IPC_PASSWORD = "ASF_IPC_PASSWORD"

LOG = logger.set_logger('ASFBot')

parser = argparse.ArgumentParser()

parser.add_argument("-v", "--verbosity", help="Defines log verbosity",
                    choices=['CRITICAL', 'ERROR', 'WARN', 'INFO', 'DEBUG'], default='INFO')
parser.add_argument("--host", help="ASF IPC host. Default: 127.0.0.1", default='127.0.0.1')
parser.add_argument("--port", help="ASF IPC port. Default: 1242", default='1242')
parser.add_argument("--password", help="ASF IPC password.", default=None)
parser.add_argument("--tg_host", help="Telegram API host. Default: api.telegram.org", default="api.telegram.org")
parser.add_argument("--token", type=str,
                    help="Telegram API token given by @botfather.", default=None)
parser.add_argument("--alias", type=str, help="Telegram alias of the bot owner.", default=None)
args = parser.parse_args()

logger.set_level(args.verbosity)

# Telegram related environment variables.
try:
    args.token = os.environ[_ENV_TELEGRAM_BOT_TOKEN]
except KeyError as key_error:
    if not args.token:
        LOG.critical(
            "No telegram bot token provided. Please do so using --token argument or %s environment variable.", _ENV_TELEGRAM_BOT_TOKEN)
        exit(1)

try:
    args.alias = os.environ[_ENV_TELEGRAM_USER_ALIAS]
except KeyError as key_error:
    if not args.alias:
        LOG.critical(
            "No telegram user alias provided. Please do so using --alias argument or %s environment variable.", _ENV_TELEGRAM_USER_ALIAS)
        exit(1)

# ASF IPC related environment variables.
try:
    args.host = os.environ[_ENV_ASF_IPC_HOST]
except KeyError as key_error:
    pass
try:
    args.port = os.environ[_ENV_ASF_IPC_PORT]
except KeyError as key_error:
    pass
try:
    args.password = os.environ[_ENV_ASF_IPC_PASSWORD]
except KeyError as key_error:
    if not args.password:
        LOG.debug("No IPC Password provided.")
    pass
try:
    args.tg_host = os.environ[_ENV_TELEGRAM_API_HOST]
except KeyError as key_error:
    if not args.tg_host:
        LOG.debug("No Telegram API Host provided.")
    pass

# Sanitize input
if args.alias[0] == '@':
    args.alias = args.alias[1:]

args.token = args.token.strip()
args.alias = args.alias.strip()
args.host = args.host.strip()
args.port = args.port.strip()
args.tg_host = args.tg_host.strip()

if args.password:
    args.password = args.password.strip()

LOG.info("Starting up bot...")
LOG.debug("Telegram api host: %s", args.tg_host)
LOG.debug("Telegram token: %s", args.token)
LOG.debug("User alias: %s", args.alias)
LOG.debug("ASF IPC host: %s", args.host)
LOG.debug("ASF IPC port: %s", args.port)

asf_connector = ASFConnector(args.host, args.port, password=args.password)

try:
    asf_info = asf_connector.get_asf_info()
    LOG.info('ASF Instance replied: {}'.format(asf_info['Message']))
    if not asf_info['Success']:
        LOG.warning('ASF Instance message was unsuccesful. %s', str(asf_info))

except Exception as e:
    LOG.critical("Couldn't communicate with ASF. Host: '%s' Port: '%s' \n %s",
                 args.host, args.port, str(e))
    exit(1)
telebot.apihelper.API_URL = f"https://{args.tg_host}/bot{{0}}/{{1}}"
LOG.debug(f"TG SET HOST: {telebot.apihelper.API_URL}")

bot = telebot.TeleBot(args.token)


def is_user_message(message):
    """ Returns if a message is from the owner of the bot comparing it to the user alias provided on startup. """
    username = message.chat.username
    return username == args.alias


@bot.message_handler(func=is_user_message, commands=['status'])
def status_command(message):
    LOG.debug("Received status message: %s", str(message))
    match = re.search(_REGEX_COMMAND, message.text)
    if not match:
        reply_to(message, "Invalid command. Usage:\n<code>/status &lt;bot&gt;</code>")
        return
    bot_arg = match.group('bot') if match.group('bot') else 'ASF'
    response = asf_connector.get_bot_info(bot_arg)
    LOG.info("Response to status message: %s", str(response))
    reply_to(message, "<code>" + str(response) + "</code>")


@bot.message_handler(commands=['redeem'])
def redeem_command(message):
    LOG.debug("Received redeem message: %s", str(message))
    match = re.search(_REGEX_COMMAND_BOT_ARGS, message.text)
    if not match:
        reply_to(message, "Missing arguments. Usage:\n<code>/redeem &lt;bot&gt; &lt;keys&gt;</code>")
        return
    bots = match.group('bot') if match.group('bot') else 'ASF'
    keys = match.group('arg')
    response = asf_connector.bot_redeem(bots, keys)
    LOG.info("Response to redeem message: %s", str(response))
    reply_to(message, "<code>" + str(response) + "</code>")


@bot.message_handler(func=is_user_message, regexp=_REGEX_COMMAND_RAW)
def command_handler(message):
    """
    Handler only for unsupported commands.
    """
    LOG.debug("Received command: %s", str(message))
    match = re.search(_REGEX_COMMAND_RAW, message.text)
    if not match:
        reply_to(message, "Invalid command.")
        return
    command = match.group('input')
    try:
        asf_response = asf_connector.send_command(command)
        LOG.info("Command: {}. Response: {}".format(message.text, asf_response))
        response = replace_html_entities(asf_response)
    except requests.exceptions.HTTPError as ex:
        status_code = ex.response.status_code
        LOG.error(ex)
        response = 'Error sending command. ASF status code: <code>{}</code>'.format(status_code)
    reply_to(message, response)


@bot.message_handler(content_types=['text'])
def check_for_cdkeys(message):
    """
    Sync handler for the rest of the messages. It searchs for cdkeys and redeems them.
    """
    cdkeys = set(_REGEX_CDKEY.findall(message.text))
    if len(cdkeys) > 0:
        response = asf_connector.bot_redeem('ASF', cdkeys)
        reply_to(message, "<code>" + str(response) + "</code>")
    else:
        LOG.debug("Bypassed message: %s \n from user alias %s.",
                  message.text, message.chat.username)


def reply_to(message, text, **kwargs):
    try:
        bot.reply_to(message, text, parse_mode="html", **kwargs)
    except Exception as ex:
        bot.reply_to(message, "There was a Telegram error sending the message:\n" + text +
                     ". \n Check the bot log for more details.")
        LOG.exception(ex)


def replace_html_entities(message: str):
    return message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


try:
    LOG.debug("Polling started")
    bot.polling(none_stop=True)
except Exception as e:
    LOG.exception(e)
    LOG.critical(str(e))

