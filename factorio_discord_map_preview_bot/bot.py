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
        self.entity_emojis = {}

    def format_entity_count(self, count):
        if count > 10000000:
            return '{:.1f}M'.format(count / 1000000)
        if count > 10000:
            return '{:.1f}l'.format(count / 1000)
        return int(count)

    def format_entity_name(self, name):
        try:
            return self.entity_emojis[name]
        except KeyError:
            return '[{}]'.format(name)

    def format_entity(self, name, count):
        return '{} {}'.format(self.format_entity_name(name),
                              self.format_entity_count(count))

    def format_dir(self, fmt, *args, **kwargs):
        return os.path.join(self.dir, fmt.format(*args, **kwargs))

    async def on_ready(self):
        logger.info('Logged in as {}#{}', self.user.name, self.user.id)
        if self.owner_id:
            self.owner = await self.get_user_info(self.owner_id)
            logger.info('Got owner info {}', self.owner)
            await self.send_message(self.owner, "I'm ready")

        for emoji in self.get_all_emojis():
            name = emoji.name.replace('_', '-')
            if name in self.preview.entities:
                self.entity_emojis[name] = emoji
                logger.info('Found emoji for {}: {}', name, emoji)

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
                entities = await self.preview(maps_gen_settings_path, image_path, log_path)
            except Exception as e:
                await self.send_message(
                    message.channel,
                    content="Sorry {}, something went wrong generating your map preview.".format(message.author.mention)
                )
                raise e

            logger.info('completed request {} in {} s', uid, time.time() - time_start)
            entity_info = ', '.join(self.format_entity(*e) for e in entities.items())
            await self.send_file(
                message.channel, image_path,
                content="Here's your preview {}: {}".format(message.author.mention, entity_info)
            )
