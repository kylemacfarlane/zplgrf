import base64
import binascii
import re
import zlib
from ctypes import c_ushort

from .base import RasterLabel, RasterLabelCollection, RasterLabelException


CRC_CCITT_TABLE = None


def _calculate_crc_ccitt(data):
    """
    All CRC stuff ripped from PyCRC, GPLv3 licensed
    """
    global CRC_CCITT_TABLE
    if not CRC_CCITT_TABLE:
        crc_ccitt_table = []
        for i in range(0, 256):
            crc = 0
            c = i << 8

            for j in range(0, 8):
                if (crc ^ c) & 0x8000:
                    crc = c_ushort(crc << 1).value ^ 0x1021
                else:
                    crc = c_ushort(crc << 1).value

                c = c_ushort(c << 1).value

            crc_ccitt_table.append(crc)
            CRC_CCITT_TABLE = crc_ccitt_table

    crc_value = 0x0000  # XModem version

    for c in data:
        tmp = ((crc_value >> 8) & 0xff) ^ c
        crc_value = ((crc_value << 8) & 0xff00) ^ CRC_CCITT_TABLE[tmp]

    return crc_value


RE_COMPRESSED = re.compile(r'[G-Zg-z]+.')
RE_UNCOMPRESSED = re.compile(r'((.)\2{1,})')
RE_BINARY_SPLIT = re.compile(r'((.)\2*)')


class ZebraRasterLabel(RasterLabel):
    @staticmethod
    def _calc_crc(data):
        return '%04X' % _calculate_crc_ccitt(data)

    @classmethod
    def _from_grf(cls, data, width, filesize):
        base64_encoded = False
        base64_compressed = False
        crc = None

        if data.startswith(':Z64') or data.startswith(':B64'):
            if data.startswith(':Z'):
                base64_compressed = True
            base64_encoded = True
            crc = data[-4:]
            data = data[5:-5]

        if base64_encoded:
            if crc is not None:
                if crc != cls._calc_crc(data.encode('ascii')):
                    raise RasterLabelException('Bad CRC')
            data = base64.b64decode(data)
            if base64_compressed:
                data = zlib.decompress(data)
        else:
            to_decompress = set(RE_COMPRESSED.findall(data))
            to_decompress = sorted(to_decompress, reverse=True)
            for compressed in to_decompress:
                repeat = 0
                char = compressed[-1:]
                for i in compressed[:-1]:
                    if i == 'z':
                        repeat += 400
                    else:
                        value = ord(i.upper()) - 70
                        if i == i.lower():
                            repeat += value * 20
                        else:
                            repeat += value
                data = data.replace(compressed, char * repeat)

            rows = []
            row = ''
            for c in data:
                if c == ':':
                    rows.append(rows[-1])
                    continue
                elif c == ',':
                    row = row.ljust(width * 2, '0')
                else:
                    row += c
                if len(row) == width * 2:
                    rows.append(binascii.unhexlify(row))
                    row = ''
            data = b''.join(rows)

        if len(data) != filesize:
            raise RasterLabelException('Bad file size')

        return cls.from_bytes(data, width)

    @classmethod
    def extract_printer_rasters(cls, data):
        data = data.replace('\n', '').replace('\r', '')
        data = data.replace('^', '\n^').replace('~', '\n~')
        data = data.split('\n')

        rasters = []
        for line in data:
            if line.startswith('~DG'):
                # Always GRF?
                line = line[5:].split(',', 3)
                filesize = int(line[1])
                width = int(line[2])
                line = line[3]
                rasters.append(cls._from_grf(line, width, filesize))
            elif line.startswith('~DY'):
                # Can contain multiple image formats and even fonts etc
                line = line[5:].split(',', 5)
                if line[2] not in ('B', 'G', 'P', 'H'):
                    # Non-graphic file (fonts etc) that we'll never support
                    continue
                if line[2] != 'G':
                    # Other image formats are possible but I don't want
                    # to guess how they might work without seeing real ZPL
                    # that contains them
                    raise RasterLabelException(
                        'Unimplemented graphic format: %s' % line[2]
                    )
                filesize = int(line[3])
                width = int(line[4])
                line = line[5]
                rasters.append(cls._from_grf(line, width, filesize))
            elif line.startswith('^GF'):
                # ^GF is tricky because it doesn't tell us what image type it
                # contains
                line = line[3:].split(',', 4)
                if line[0] != 'A':
                    # "B" is binary and probably PNGs, BMPs, etc but I don't
                    # want to guess how they might work without seeing real ZPL
                    # that contains them
                    # "C" is compressed binary
                    raise RasterLabelException(
                        'Unimplemented compression: %s' % line[0]
                    )
                filesize = int(line[2])
                width = int(line[3])
                line = line[4]
                rasters.append(cls._from_grf(line, width, filesize))

        return RasterLabelCollection(rasters)

    def to_printer_raster(self, compression=3):
        """
        Compression:
            3 = ZB64/Z64, base64 encoded DEFLATE compressed - best compression
            2 = ASCII hex encoded run length compressed - most compatible
            1 = B64, base64 encoded - pointless?
        """
        if compression == 3:
            data = base64.b64encode(zlib.compress(self.bytes))
            data = ':Z64:%s:%s' % (data.decode('ascii'), self._calc_crc(data))
        elif compression == 1:
            data = base64.b64encode(self.bytes)
            data = ':B64:%s:%s' % (data.decode('ascii'), self._calc_crc(data))
        else:
            lines = []
            last_unique_line = None

            for line in self.bytes_rows:
                line = binascii.hexlify(line).decode('ascii').upper()
                if line.endswith('00'):
                    line = line.rstrip('0')
                    if len(line) % 2:
                        line += '0'
                    line += ','
                if line == last_unique_line:
                    line = ':'
                else:
                    last_unique_line = line
                lines.append(line)

            data = '\n'.join(lines)
            to_compress = set(RE_UNCOMPRESSED.findall(data))
            to_compress = sorted(to_compress, reverse=True)
            for uncompressed in to_compress:
                uncompressed = uncompressed[0]
                repeat = len(uncompressed)
                compressed = ''
                while repeat >= 400:
                    compressed += 'z'
                    repeat -= 400
                if repeat >= 20:
                    value = repeat // 20
                    repeat -= value * 20
                    compressed += chr(value + 70).lower()
                if repeat > 0:
                    compressed += chr(repeat + 70)
                data = data.replace(uncompressed, compressed + uncompressed[0])

            data = data.replace('\n', '')

        return {
            'data': data,
            'filesize': self.filesize,
            'width': self.width // 8
        }


class SimpleZebraPrinter:
    """
    A very simple class to wrap up the rasters in enough commands to test them
    on a real printer.

    If you need more options you should create your own class. Do not open
    issues or pull requests trying to expand this class into a full blown
    printer driver.

    When using ~DG/^XG/^ID I can't get the raster label to reliably delete from
    every printer I tried. However when using ^GF the rasters worked fine on
    Zebra printers but were sometimes cut off on Citizen printers. Citizen's
    ZPL emulation guide from 2008 says ^GF is unsupported.

    If you did want to use ^GF it would be like the following:

        '^GF%s,%s,%s,%s,%s' % (
            'A',  # Even ZB64 is sent as uncompressed ASCII
            raster['filesize'],  # Binary byte count
            raster['filesize'],  # Same as above for uncompressed data
            raster['width'],  # Bytes per row
            raster['data']
        )
    """
    @staticmethod
    def print(
        rasters,
        filename='RASTER',
        media_tracking='Y',
        memory='R',
        origin=(0, 0),
        print_mode='T',
        print_mode_last='C',
    ):
        zpl = []

        for i, raster in enumerate(rasters, 1):
            zpl += [
                '~DG%s:%s.GRF,%s,%s,%s' % (
                    memory,
                    filename,
                    raster['filesize'],  # Total bytes
                    raster['width'],  # Bytes per row
                    raster['data']
                ),  # Transfer image
                '^XA',  # Start label format
                '^MM%s' % (
                    print_mode_last if i == len(rasters) else print_mode
                ),
                '^MN%s' % media_tracking,
                '^LH%s,%s' % origin,  # Label home
                '^FO%s,%s' % origin,  # Field origin
                '^XG%s:%s.GRF,1,1' % (memory, filename),  # Draw image
                '^XZ',  # End label format
                '^XA^ID%s:%s.GRF^FS^XZ' % (memory, filename)  # Delete image
            ]

        return ''.join(zpl)
