import traceback

from .logging import logger


class BotError(Exception):
    def __init__(self, *args, **kwargs):
        message = 'Exception ({}, {}): {}'.format(args, kwargs, traceback.format_exc())
        logger.error(message)
        super().__init__(*args, **kwargs)

