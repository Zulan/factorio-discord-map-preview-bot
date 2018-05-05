import click
import click_log
import discord
import os

from .logging import logger
from .bot import Bot
from .preview import SimplePreview

click_log.basic_config(logger)
logger.setLevel('INFO')


@click.command()
@click.argument('factorio-binary', type=click.Path(exists=True, dir_okay=False))
@click.argument('discord-token-file', type=click.File('r'))
@click.option('--dir',
              type=click.Path(exists=True, file_okay=False,
                              dir_okay=True, readable=True, writable=True),
              default=os.getcwd())
@click.option('--owner-id', type=int)
@click_log.simple_verbosity_option(logger)
def main(factorio_binary, discord_token_file, dir, owner_id):
    preview = SimplePreview(factorio_binary)
    bot = Bot(preview, dir, owner_id)
    token = discord_token_file.read().strip()
    bot.run(token)
