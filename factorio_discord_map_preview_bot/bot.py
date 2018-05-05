import discord
import uuid
import os
import time
import traceback

from .map_string import map_string_to_file
from .logging import logger


class Bot(discord.Client):
    def __init__(self, preview, dir, owner_id=None):
        super().__init__()
        self.preview = preview
        self.dir = dir
        self.owner_id = owner_id
        self.owner = None

    def format_dir(self, fmt, *args, **kwargs):
        return os.path.join(self.dir, fmt.format(*args, **kwargs))

    async def on_ready(self):
        logger.info('Logged in as {}#{}', self.user.name, self.user.id)
        if self.owner_id:
            self.owner = await self.get_user_info(self.owner_id)
            logger.info('Got owner info {}', self.owner)
            await self.send_message(self.owner, "I'm ready")

    async def on_error(self, event_method, *args, **kwargs):
        message = 'Exception in {} ({}, {}): {}'.format(event_method, args, kwargs, traceback.format_exc())
        logger.error(message)
        if self.owner:
            await self.send_message(self.owner, message)

    async def on_message(self, message):
        cmd = message.content.split(' ', 2)
        if len(cmd) >= 2 and cmd[0] == '!mapPreview':
            logger.info('Received command by {} in {}: {}',
                        message.author.mention, message.channel, cmd)
            time_start = time.time()
            try:
                map_string = cmd[1]
                uid = uuid.uuid4().hex
                image_path = self.format_dir('preview-{}.png', uid)
                maps_gen_settings_path = self.format_dir('mapstring-{}.lua', uid)
                log_path = self.format_dir('log-{}.log', uid)

                map_string_to_file(map_string, maps_gen_settings_path)
            except Exception as e:
                await self.send_message(
                    message.channel,
                    content="Sorry {}, something went wrong parsing your map string.".format(message.author.mention)
                )
                raise e

            try:
                self.preview(maps_gen_settings_path, image_path, log_path)
            except Exception as e:
                await self.send_message(
                    message.channel,
                    content="Sorry {}, something went wrong generating your map preview.".format(message.author.mention)
                )
                raise e

            logger.info('completed request {} in {} s', uid, time.time() - time_start)
            await self.send_file(
                message.channel, image_path,
                content="Here's your preview {}, have fun.".format(message.author.mention)
            )
