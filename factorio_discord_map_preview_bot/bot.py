import uuid
import os
import time
import traceback
from collections import OrderedDict
from numbers import Number

import discord

from .map_string import parse_map_string, dump_map_gen_settings, known_version
from .logging import logger
from .error import BotError


def get_options(command_list, options, flags=[]):
    d = OrderedDict()
    while len(command_list) >= 1:
        o = command_list[0]
        if o in flags:
            d[o] = True
        elif o in options:
            d[o] = options[o]()


class Bot(discord.Client):
    def __init__(self, preview_generator, dir, owner_id=None):
        super().__init__()
        self.generate_preview = preview_generator
        self.dir = dir
        self.owner_id = owner_id
        self.owner = None
        self.entity_emojis = {}

    def format_entity_count(self, count):
        if not isinstance(count, Number):
            return '??'
        if count > 1000000:
            return '{:.1f}M'.format(count / 1000000)
        if count > 1000:
            return '{:.1f}k'.format(count / 1000)
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
            await self.owner.send("I'm ready")

        for emoji in self.emojis:
            name = emoji.name.replace('_', '-')
            if name in self.generate_preview.entities:
                self.entity_emojis[name] = emoji
                logger.info('Found emoji for {}: {}', name, emoji)

    async def on_error(self, event_method, *args, **kwargs):
        message = 'Exception in {} ({}, {}): {}'.format(event_method, args, kwargs, traceback.format_exc())
        logger.error(message)
        if self.owner:
            await self.owner.send(message)

    async def on_message(self, message):
        if message.content.startswith('!'):
            logger.debug('Received command by {} in {}: {}',
                         message.author, message.channel, message.content)
            cmd = message.content.split(' ')
            if len(cmd) >= 1:
                if cmd[0] == '!mapPreview':
                    await self.preview(cmd[1:], message.channel, message.author)
                if cmd[0] == '!info':
                    await self.info(message.author)

    async def info(self, author):
        fmt =  "Hi, I'm the MapPreviewBot!\n"
        fmt += "I generate Factorio map previews in Discord.\n"
        fmt += "I know the following commands:\n"
        fmt += "`!mapPreview`, `!info`\n"
        fmt += "My owner is {owner}, let him know if something is wrong.\n"
        fmt += "You can find my source code at https://github.com/Zulan/factorio-discord-map-preview-bot/.\n"
        fmt += "I use Factorio Version {factorio_version} and know map exchange strings up to {mapstring_version}."

        text = fmt.format(
            owner=self.owner.mention,
            factorio_version=await self.generate_preview.get_version_str(),
            mapstring_version=known_version,
        )
        await author.send(content=text)

    async def preview(self, command, channel, author):
        async with channel.typing():
            time_start = time.time()
            try:
                scale = None
                while command[0].startswith('--'):
                    if command[0] == '--scale':
                        scale = float(command[1])
                        if scale < 0.1:
                            raise BotError('selected scale is too small')
                        if scale > 100:
                            raise BotError('selected scale is too large')
                        command = command[2:]
                    else:
                        raise BotError("unknown option")

                map_string = ''.join(command)
                uid = uuid.uuid4().hex
                image_path = self.format_dir('{}.png', uid)
                maps_gen_settings_path = self.format_dir('{}.json', uid)
                log_path = self.format_dir('{}.log', uid)

                map_gen_settings, version_mismatch = parse_map_string(map_string)
                if version_mismatch:
                    await channel.send(
                        content='The version of this map exchange string is too recent' 
                                '({}, i know up to {}), there may be problems.'.format(*version_mismatch)
                    )
                dump_map_gen_settings(map_gen_settings, maps_gen_settings_path)

            except BotError as be:
                await channel.send('Sorry {}, {}.'.format(author.mention, be))
                logger.info('BotError: {}', be)
                return
            except Exception as e:
                await channel.send(content="Sorry {}, something went wrong parsing your map string.".format(author.mention))
                raise e

            try:
                entities = await self.generate_preview(maps_gen_settings_path, image_path, log_path, scale)
            except BotError as be:
                await channel.send('Sorry {}, {}'.format(author.mention, be))
                logger.info('BotError: {}', be)
                return
            except Exception as e:
                await channel.send("Sorry {}, something went wrong generating your map preview.".format(author.mention))
                raise e

            logger.info('completed request {} in {} s', uid, time.time() - time_start)
            entity_info = ', '.join(self.format_entity(*e) for e in entities.items())
            await channel.send(
                "Here's your preview {}: {}".format(author.mention, entity_info),
                file=discord.File(image_path)
            )
