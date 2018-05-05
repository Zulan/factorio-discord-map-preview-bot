import click
import click_log
import discord
import asyncio
import uuid
import os
import subprocess
import time

from .map_string import map_string_to_file
from .logging import logger


click_log.basic_config(logger)
logger.setLevel('INFO')


@click.command()
@click.argument('factorio-binary')
@click.argument('discord-token-file', type=click.File('r'))
@click.argument('image-dir')
@click.option('--max-instances', default=1)
@click_log.simple_verbosity_option(logger)
def cli(factorio_binary, discord_token_file, image_dir, max_instances):
    client = discord.Client()
    semaphore = asyncio.BoundedSemaphore(max_instances)
    token = discord_token_file.read().strip()

    @client.event
    async def on_ready():
        logger.info('Logged in as {}#{}', client.user.name, client.user.id)

    @client.event
    async def on_message(message):
        cmd = message.content.split(' ', 2)
        if len(cmd) >= 2 and cmd[0] == '!mapPreview':
            logger.info('Received command by {} in {}: {}', message.author, message.channel, cmd)
            time_start = time.time()
            try:
                map_string = cmd[1]
                uid = uuid.uuid4().hex
                image_path = os.path.join(image_dir, 'preview-{}.png'.format(uid))
                maps_gen_settings_path = os.path.join(image_dir, 'mapstring-{}.lua'.format(uid))
                log_path = os.path.join(image_dir, 'log-{}.log'.format(uid))

                map_string_to_file(map_string, maps_gen_settings_path)
            except Exception as e:
                await client.send_message(
                    message.channel,
                    content="Sorry {}, something went wrong parsing your map string.".format(message.author.mention)
                )
                raise e

            await semaphore.acquire()
            try:
                with open(log_path, 'w') as log_file:
                    process = await asyncio.create_subprocess_exec(
                        factorio_binary,
                        '--generate-map-preview', image_path,
                        '--map-gen-settings', maps_gen_settings_path,
                        stdout=log_file, stderr=subprocess.STDOUT
                    )
                    # TODO use wait_for with timeout
                await process.wait()
            except Exception as e:
                await client.send_message(
                    message.channel,
                    content="Sorry {}, something went wrong generating your map preview.".format(message.author.mention)
                )
                raise e
            finally:
                # No context manager?! What is this stone age madness!
                semaphore.release()

            logger.info('completed request {} in {} s', uid, time.time() - time_start)
            await client.send_file(
                message.channel, image_path,
                content="Here's your preview {}, have fun.".format(message.author.mention)
            )

    client.run(token)
