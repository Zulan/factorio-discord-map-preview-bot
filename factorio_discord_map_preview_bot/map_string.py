import base64
import zlib
import io
import struct
import json
from collections import OrderedDict
from abc import ABC, abstractmethod

from error import BotError


known_version = (0, 17, 45, 1)


def parse_frame(map_string):
    return map_string.lstrip('>').rstrip('<').replace('\n', '').replace(' ', '')


class Deserializer:
    def __init__(self, buffer):
        self._buffer = buffer
        self.version = self.unpack('hhhh')

    def parse_uint(self):
        num, = self.unpack('B')
        if num < 255:
            return num
        num, = self.unpack('I')
        return num

    def unpack(self, fmt):
        fmt = '<' + fmt
        size = struct.calcsize(fmt)
        buf = self._buffer.read(size)
        return struct.unpack(fmt, buf)


class FactorioType(ABC):
    @abstractmethod
    def native(self):
        pass

    def __repr__(self):
        return str(self)


def native(thing):
    if isinstance(thing, FactorioType):
        return thing.native()
    return thing


class FactorioSingleType(FactorioType):
    __slots__ = 'value',

    def __str__(self):
        return str(self.value)

    def native(self):
        return self.value


class FactorioStructType(FactorioType):
    def __str__(self):
        return str(self.__dict__)

    def native(self):
        return {key: native(value) for key, value in self.__dict__.items()}


class String(FactorioSingleType):
    def __init__(self, deserializer):
        length = deserializer.parse_uint()
        self.value = deserializer._buffer.read(length).decode('ascii')


class MapGenSize(FactorioSingleType):
    def __init__(self, deserializer):
        if deserializer.version >= (0, 17, 0, 0):
            self.value, = deserializer.unpack('f')
        else:
            self.value, = deserializer.unpack('B')

    def __str__(self):
        if isinstance(self.value,float):
            return str(self.value)
        else:
            return {
                0: 'none',
                1: 'very-low',
                2: 'low',
                3: 'normal',
                4: 'high',
                5: 'very-high',
            }[self.value]

    def native(self):
        return str(self)


class FrequencySizeRichness(FactorioStructType):
    def __init__(self, deserializer):
        self.frequency = MapGenSize(deserializer)
        self.size = MapGenSize(deserializer)
        self.richness = MapGenSize(deserializer)


class StringMap(FactorioType):
    def __init__(self, deserializer, value_type):
        length = deserializer.parse_uint()
        self.values = OrderedDict()
        for _ in range(length):
            key = String(deserializer)
            value = value_type(deserializer)
            self.values[key] = value

    def __str__(self):
        return str(self.values)

    def native(self):
        return {native(key): native(value) for key, value in self.values.items()}


class Vector(FactorioType):
    def __init__(self, deserializer, value_type):
        length = deserializer.parse_uint()
        self.values = [
            value_type(deserializer) for _ in range(length)
        ]

    def __str__(self):
        return str(self.values)

    def native(self):
        return [native(value) for value in self.values]


class Coordinate(FactorioSingleType):
    def __init__(self, deserializer):
        # It's a FixedPointNumber
        x, = deserializer.unpack('i')
        self.value = x / (1 << 8)


class MapPosition(FactorioStructType):
    def __init__(self, deserializer):
        xdiff, = deserializer.unpack('h')
        if xdiff == 32767:
            self.x = Coordinate(deserializer)
            self.y = Coordinate(deserializer)
        else:
            ydiff, = deserializer.unpack('h')
            # FIXME add last loaded position coordinate type?!
            self.x = xdiff
            self.y = ydiff


class RealOrientation(FactorioSingleType):
    def __init__(self, deserializer):
        self.value, = deserializer.unpack('f')


class BoundingBox(FactorioStructType):
    def __init__(self, deserializer):
        self.left_top = MapPosition(deserializer)
        self.right_bottom = MapPosition(deserializer)
        self.orientation = RealOrientation(deserializer)


class CliffSettings(FactorioStructType):
    def __init__(self, deserializer):
        self.name = String(deserializer)
        self.cliff_elevation0, self.cliff_elevation_interval \
            = deserializer.unpack('ff')


class AutoplaceSettings(FactorioStructType):
    def __init__(self, deserializer):
        self.treat_missing_as_default, = deserializer.unpack('?')
        self.settings = StringMap(deserializer, FrequencySizeRichness)


class MapGenSettings(FactorioStructType):
    def __init__(self, deserializer):
        # Random zero byte after version, Bilka told me to ignore it
        if deserializer.version >= (0, 17, 0, 0):
            deserializer.unpack('B')
        self.terrain_segmentation = MapGenSize(deserializer)
        self.water = MapGenSize(deserializer)
        self.autoplace_controls = StringMap(deserializer, FrequencySizeRichness)

        if deserializer.version >= (0, 16, 0, 37):
            self.autoplace_settings = StringMap(deserializer, AutoplaceSettings)
            self.default_enable_all_autoplace_controls, = deserializer.unpack('?')

        self.seed, self.width, self.height = deserializer.unpack('III')
        if deserializer.version >= (0, 16, 0, 63):
            # Noone cares about the areaToGenerateAtStart
            BoundingBox(deserializer)

        self.starting_area = MapGenSize(deserializer)
        self.peaceful_mode, = deserializer.unpack('?')

        if deserializer.version >= (0, 16, 0, 22):
            self.starting_points = Vector(deserializer, MapPosition)
            self.property_expression_names = StringMap(deserializer, String)

        if deserializer.version >= (0, 16, 0, 63):
            self.cliff_settings = CliffSettings(deserializer)


def parse_map_string(map_string):
    map_string = parse_frame(map_string)
    try:
        decoded = base64.decodebytes(map_string.encode())
    except Exception:
        raise BotError('could not decode map exchange string - maybe it is incomplete')
    unzipped = zlib.decompress(decoded)
    try:
        buf = io.BytesIO(unzipped)
    except Exception:
        raise BotError('could not decompress map exchange string')
    deserializer = Deserializer(buf)
    version_mismatch = (deserializer.version, known_version) if known_version < deserializer.version else False
    try:
        map_gen_settings = MapGenSettings(deserializer)
        return map_gen_settings, version_mismatch
    except Exception:
        if version_mismatch:
            raise BotError('the version of this map exchange string {} is too recent and there was a parse error.'
                           .format(version_mismatch))
        raise BotError('could not parse map exchange string structure')


def dump_map_gen_settings(map_gen_settings, path):
    with open(path, 'w') as f:
        json.dump(native(map_gen_settings), f)


if __name__ == '__main__':
    print(parse_map_string(""">>>eNpjYBBk0GVgZACCBnsgYc/BkpyfmMPAcMABhrmS8wsKUot08
4tSkYU5k4tKU1J18zNRFafmpeZW6iYlFqdCTQSbzJFZlJ+HbgJrc
Ul+Hlhk9apV9iDMWlKUmloM1ACUd7AHaeQuLUrMyyzNBeldvUrLD
mQcmGY0tuN50dAixwDC/+sZFP7/B2Eg6wFQyQMGBpjVDIxAMShg1
kjOzyspys/RLU4tKcnMS7dKLK2wSitKLSxNzUuutMotzSnJLMjJT
C3iMNAzNzUAAll0Hbn5mcUlpUWpVkmZicWcugZ6YGUGujjVYTXeT
A+sy4A1OSczLY2BQcERiJ1AbmRkZKwWWef+sGqKPSPE1XoOUMYHq
MiBJJiIJ4zh54BTSgXGMEEyxxgMPiMxIJaWAK2AquJwQDAgki0gS
UbG3rdbF3w/dsGO8c/Kj5d8kxLsGQ1dRd59MFpnB5RkB3mBCU7Mm
gkCO2FeYYCZ+cAeKnXTnvHsGRB4Y8/ICtIhAiIcLIDEAW9mBkYBP
iBrQQ+QUJBhgDnNDmaMiANjGhh8g/nkMYxx2R7dH8CAsAEZLgciT
oAIsIVwlzFCmZEOEAlJhCxQqxEDsvUpCM+dhNl4GMlqNDdgxgGyF
9BEVJACngtkTwqceMEMdwQwBC+ww3gO9Q7MDAjwwZ7BJ/BxFwCn7
9XS<<<"""))
