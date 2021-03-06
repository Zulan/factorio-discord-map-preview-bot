import base64
import zlib
import io
import struct
import json
from collections import OrderedDict
from abc import ABC, abstractmethod

from .error import BotError


known_version = (0, 17, 51, 0)


def parse_frame(map_string):
    return map_string.lstrip('>').rstrip('<').replace('\n', '').replace(' ', '')


class Deserializer:
    def __init__(self, buffer):
        self._buffer = buffer
        self.version = self.unpack('hhhh')
        if self.version >= (0, 17, 0, 30):
            self.unpack('B')
            # probably 0 but we don't care

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
        if deserializer.version < (0, 17, 0, 77):
            self.value, = deserializer.unpack('B')
        else:
            self.value, = deserializer.unpack('f')

    def __str__(self):
        if isinstance(self.value, int):
            return {
                0: 'none',
                1: 'very-low',
                2: 'low',
                3: 'normal',
                4: 'high',
                5: 'very-high',
            }[self.value]
        return str(self.value)

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
        if deserializer.version >= (0, 17, 0, 124):
            self.richness, = deserializer.unpack('f')


class AutoplaceSettings(FactorioStructType):
    def __init__(self, deserializer):
        self.treat_missing_as_default, = deserializer.unpack('?')
        self.settings = StringMap(deserializer, FrequencySizeRichness)


class MapGenSettings(FactorioStructType):
    def __init__(self, deserializer):
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
    print(parse_map_string(""">>>eNpjYBBgUGFgYmBl5GFJzk/MYWJl5UrOLyhILdLNL0plZGXlTC4q
TUnVzc/MYWFlZUtJLU4tKmFmYGZJyQTTXKl5qbmVukmJxalAHmt6UWJ
xMZDBkVmUnwc1gaU4MS+FlZGZtbgkPy+VFWhDSVFqajETIyN3aVFiXm
ZpLkghMwMrA+O7mij2dRwMDKy8DAz/6xkM/v8HYSDrAgMDGAMBCyMjU
AAGWJNzMtPSGBgaXBgYFBwZGRirRda5P6yaYs8IkddzgDI+QEUidkNF
HrRCGRGroYyOw1CGw3wYox7G6HdgNAaDz/YIBsSuEqDJUEs4HBAMiGQ
LWJKx9+3WBd+PXbBj/LPy4yXfpAR7xkzZUF+B0vd2QEl2oAZGJjgxay
YI7IT5gAFm5gN7qNRNe8azZ0DgjT0jK0iHCIhwsAASB7yZGRgF+ICsB
T1AQkGGAeY0O5gxIg6MaWDwDeaTxzDGZXt0f6g4MNqADJcDESdABNhC
uMsYocxIB4iEJEIWqNWIAdn6FITnTsJsPIxkNZobVGBuMHHA4gU0ERW
kgOcC2ZMCJ14wwx0BDMEL7DAeMG6ZGRDgg73uLNd5APo0kTo=<<<"""))