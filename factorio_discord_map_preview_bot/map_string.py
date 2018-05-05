import base64
import zlib
import io
import struct


def unpack(stream, fmt):
    size = struct.calcsize('!' + fmt)
    buf = stream.read(size)
    return struct.unpack(fmt, buf)


def parse_map_gen_settings(buf):
    pass


def parse_map_settings(buf):
    pass


def parse_frame(map_string):
    return map_string.lstrip('>').rstrip('<').replace('\n', '').replace(' ', '')


def parse_uint(buf):
    num, = unpack(buf, 'B')
    if num < 255:
        return num
    num, = unpack(buf, 'I')
    return num


def parse_string(buf):
    length = parse_uint(buf)
    str = buf.read(length).decode()
    return str


def parse_scale_byte(buf):
    b, = unpack(buf, 'B')
    return {
        255: 'WTF',
        0: 'none',
        1: 'very-low',
        2: 'low',
        3: 'normal',
        4: 'high',
        5: 'very-high',
    }[b]


def parse_autoplace_control(buf):
    apc = dict()
    apc['frequency'] = parse_scale_byte(buf)
    apc['size'] = parse_scale_byte(buf)
    apc['richness'] = parse_scale_byte(buf)
    return apc


def parse_dict(buf, key_parser=parse_string, value_parser=parse_autoplace_control):
    length = parse_uint(buf)
    #return {
    #    key_parser(buf): value_parser(buf)
    #    for _ in range(length)
    #}
    d = dict()
    for i in range(length):
        key = key_parser(buf)
        d[key] = value_parser(buf)

    return d


def parse_vector(buf, parser):
    length = parse_uint(buf)
    return [parser(buf) for _ in range(length)]


def parse_coordinate(buf):
    x, = unpack(buf, 'i')
    return x / (1 << 8)


def parse_map_position(buf):
    xdiff, = unpack(buf, 'h')
    if xdiff == 32767:
        x = parse_coordinate(buf)
        y = parse_coordinate(buf)
    else:
        ydiff, = unpack(buf, 'h')
        # TODO last loaded position?!
        x = xdiff
        y = ydiff

    return {'x': x, 'y': y}


def parse_real_orientation(buf):
    orientation, = unpack(buf, 'f')
    return orientation


def parse_bounding_box(buf):
    bb = dict()
    bb['left-top'] = parse_map_position(buf)
    bb['right-bottom'] = parse_map_position(buf)
    bb['orientation'] = parse_real_orientation(buf)
    return bb


def parse_cliff_settings(buf):
    cs = dict()
    cs['name'] = parse_string(buf)
    cs['cliff_elevation0'], = unpack(buf, 'f')
    cs['cliff_elevation_interval'], = unpack(buf, 'f')
    return cs


def parse_map_string(map_string):
    map_string = parse_frame(map_string)

    decoded = base64.decodebytes(map_string.encode())
    unzipped = zlib.decompress(decoded)
    buf = io.BytesIO(unzipped)

    mgs = dict()

    version = unpack(buf, 'hhhh')
    print('parsed version {}'.format(version))

    mgs['terrain_segmentation'] = parse_scale_byte(buf)
    mgs['water'] = parse_scale_byte(buf)
    mgs['autoplace_controls'] = parse_dict(buf)

    # TODO?!
    _,_ = unpack(buf, 'bb')
    mgs['seed'], mgs['width'], mgs['height'] = unpack(buf, 'III')
    if version >= (0, 16, 0, 63):
        area_to_generate_at_start = parse_bounding_box(buf)
        # noone cares about this

    mgs['starting_area'] = parse_scale_byte(buf)
    print(mgs['starting_area'])
    mgs['peaceful_mode'], = unpack(buf, '?')

    if version >= (0, 16, 0, 22):
        starting_points = parse_vector(buf, parse_map_position)
        property_expression_names = parse_dict(buf, parse_string, parse_string)

    if version >= (0, 16, 0, 63):
        mgs['cliff_settings'] = parse_cliff_settings(buf)

    # don't care about the rest
    return mgs


def to_lua_str(something):
    if isinstance(something, dict):
        s = '{\n'
        first = True
        for key, value in something.items():
            if first:
                first = False
            else:
                s += ',\n'
            s += '"{}": {}'.format(key, to_lua_str(value))
        s += '}\n'
        return s
    elif isinstance(something, str):
        return '"{}"'.format(something)
    elif isinstance(something, bool):
        return {True: 'true', False: 'false'}[something]
    return str(something)


def map_string_to_file(map_string, path):
    with open(path, 'w') as f:
        f.write(to_lua_str(parse_map_string(map_string)))


if __name__ == '__main__':
    print(to_lua_str(parse_map_string(""">>>eNpjYBBgUGFgYmBl5GFJzk/MYWJl5UrOLyhILdLNL0plZGXlTC4q
TUnVzc/MYWFlZUtJLU4tKmFmYGZJyQTTXKl5qbmVukmJxalAHmt6UWJ
xMZDBkVmUnwc1gaU4MS+FlZGZtbgkPy+VFWhDSVFqajETIyN3aVFiXm
ZpLkghMwMrA+O7mij2dRwMDKy8DAz/6xkM/v8HYSDrAgMDGAMBCyMjU
AAGWJNzMtPSGBgaXBgYFBwZGRirRda5P6yaYs8IkddzgDI+QEUidkNF
HrRCGRGroYyOw1CGw3wYox7G6HdgNAaDz/YIBsSuEqDJUEs4HBAMiGQ
LWJKx9+3WBd+PXbBj/LPy4yXfpAR7xkzZUF+B0vd2QEl2oAZGJjgxay
YI7IT5gAFm5gN7qNRNe8azZ0DgjT0jK0iHCIhwsAASB7yZGRgF+ICsB
T1AQkGGAeY0O5gxIg6MaWDwDeaTxzDGZXt0f6g4MNqADJcDESdABNhC
uMsYocxIB4iEJEIWqNWIAdn6FITnTsJsPIxkNZobVGBuMHHA4gU0ERW
kgOcC2ZMCJ14wwx0BDMEL7DAeMG6ZGRDgg73uLNd5APo0kTo=<<<""")))