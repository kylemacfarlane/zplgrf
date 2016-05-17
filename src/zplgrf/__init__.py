import base64
import binascii
from ctypes import c_ushort
from io import BytesIO
import os
from PIL import Image
import struct
from subprocess import Popen, PIPE
import re
import zlib


def _chunked(value, n):
    for i in range(0, len(value), n):
        yield value[i:i+n]


def _is_string(value):
    # Python 2 compatibility
    try:
        return isinstance(value, basestring)
    except NameError:
        return False


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

    is_string = _is_string(data)
    crc_value = 0x0000 # XModem version

    for c in data:
        d = ord(c) if is_string else c
        tmp = ((crc_value >> 8) & 0xff) ^ d
        crc_value = ((crc_value << 8) & 0xff00) ^ CRC_CCITT_TABLE[tmp]

    return crc_value


RE_COMPRESSED = re.compile(r'[G-Zg-z]+.')
RE_UNCOMPRESSED = re.compile(r'((.)\2{1,})')
RE_BINARY_SPLIT = re.compile(r'((.)\2*)')


class GRFException(Exception):
    pass


class GRFData(object):
    def __init__(self, width, bytes=None, hex=None, bin=None):
        self._width = width
        self._bytes = None
        self._hex = None
        self._bin = None
        if bytes:
            self._bytes = bytes
        elif hex:
            self._hex = hex
        elif bin:
            self._bin = bin

    @property
    def filesize(self):
        if self._bytes:
            return len(self._bytes)
        elif self._hex:
            return len(self._hex) // 2
        elif self._bin:
            return len(self._bin) // 8

    @property
    def height(self):
        if self._bytes:
            return len(self.bytes_rows)
        elif self._hex:
            return len(self.hex_rows)
        elif self._bin:
            return len(self.bin_rows)

    @property
    def width(self):
        return self._width * 8

    @property
    def bytes_rows(self):
        return list(_chunked(self.bytes, self._width))

    @property
    def hex_rows(self):
        return list(_chunked(self.hex, self._width * 2))

    @property
    def bin_rows(self):
        return list(_chunked(self.bin, self._width * 8))

    @property
    def bytes(self):
        if not self._bytes:
            if self._hex:
                self._bytes = binascii.unhexlify(self._hex)
            elif self._bin:
                bytes_ = []
                for binary in _chunked(self._bin, 8):
                    bytes_.append(struct.pack('B', int(binary, 2)))
                self._bytes = b''.join(bytes_)
        return self._bytes

    @property
    def hex(self):
        if not self._hex:
            if self._bytes:
                hex_ = binascii.hexlify(self._bytes).decode('ascii')
                self._hex = hex_.upper()
            elif self._bin:
                hex_ = []
                for binary in _chunked(self._bin, 8):
                    hex_.append('%02X' % int(binary, 2))
                self._hex = ''.join(hex_)
        return self._hex

    @property
    def bin(self):
        if not self._bin:
            if self._bytes:
                bin_ = []
                is_string = _is_string(self._bytes)
                for byte in self._bytes:
                    byte = ord(byte) if is_string else byte
                    bin_.append(bin(byte)[2:].rjust(8, '0'))
                self._bin = ''.join(bin_)
            elif self._hex:
                hex_ = []
                for h in _chunked(self._hex, 2):
                    hex_.append(bin(int(h, 16))[2:].rjust(8, '0'))
                self._bin = ''.join(hex_)
        return self._bin


class GRF(object):
    def __init__(self, filename, data):
        if not filename or not filename.isalnum() or len(filename) > 8:
            raise GRFException('Filename must be 1-8 alphanumeric characters')
        self.filename = filename.upper()
        self.data = data

    @staticmethod
    def _calc_crc(data):
        return '%04X' % _calculate_crc_ccitt(data)

    @staticmethod
    def _normalise_zpl(zpl):
        zpl = zpl.replace('\n', '').replace('\r', '')
        zpl = zpl.replace('^', '\n^').replace('~', '\n~')
        return zpl.split('\n')

    @classmethod
    def replace_grfs_in_zpl(cls, zpl, optimise_barcodes=True, **kwargs):
        map_ = {}
        for grf in cls.from_zpl(zpl):
            if optimise_barcodes:
                grf.optimise_barcodes(**kwargs)
            map_[grf.filename] = grf
        output = []
        for line in cls._normalise_zpl(zpl):
            if line.startswith('~DGR:'):
                line = map_[line.split('.')[0][5:]].to_zpl_line(**kwargs)
            output.append(line)
        return ''.join(output)

    @classmethod
    def from_zpl(cls, zpl):
        grfs = []
        for line in cls._normalise_zpl(zpl):
            if line.startswith('~DGR:'):
                grfs.append(cls.from_zpl_line(line))
        return grfs

    @classmethod
    def from_zpl_line(cls, line):
        line = line[5:].split(',', 3)
        filename = line[0][:-4]
        filesize = int(line[1])
        width = int(line[2])
        data = line[3]
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
                if crc != cls._calc_crc(data):
                    raise GRFException('Bad CRC')
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

        data = GRFData(width, bytes=data)

        if data.filesize != filesize:
            raise GRFException('Bad file size')

        return cls(filename, data)

    def to_zpl_line(self, compression=3, **kwargs):
        """
        Compression:
            3 = ZB64/Z64, base64 encoded DEFLATE compressed - best compression
            2 = ASCII hex encoded run length compressed - most compatible
            1 = B64, base64 encoded - pointless?
        """
        if compression == 3:
            data = base64.b64encode(zlib.compress(self.data.bytes))
            data = ':Z64:%s:%s' % (data.decode('ascii'), self._calc_crc(data))
        elif compression == 1:
            data = base64.b64encode(self.data.bytes)
            data = ':B64:%s:%s' % (data.decode('ascii'), self._calc_crc(data))
        else:
            lines = []
            last_unique_line = None

            for line in self.data.hex_rows:
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

        zpl = '~DGR:%s.GRF,%s,%s,%s' % (
            self.filename,
            self.data.filesize,
            self.data.width // 8,
            data
        )

        return zpl

    def to_zpl(
        self, quantity=1, pause_and_cut=0, override_pause=False, **kwargs
    ):
        """
        The most basic ZPL to print the GRF. Since ZPL printers are stateful
        this may not work and you may need to build your own.
        """
        zpl = [
            self.to_zpl_line(**kwargs), # Download image to printer
            '^XA', # Start Label Format
            '^FO0,0', # Field Origin to 0,0
            '^XGR:%s.GRF,1,1' % self.filename, # Draw image
            '^FS', # Field Separator
            '^PQ%s,%s,0,%s' % (
                int(quantity), # Print Quantity
                int(pause_and_cut), # Pause and cut every N labels
                'Y' if override_pause else 'N' # Don't pause between cuts
            ),
            '^XZ', # End Label Format
            '^IDR:%s.GRF' % self.filename # Delete image from printer
        ]
        return ''.join(zpl)

    @classmethod
    def from_image(cls, image, filename):
        """
        Filename is 1-8 alphanumeric characters to identify the GRF in ZPL.
        """

        source = Image.open(BytesIO(image))
        source = source.convert('1')
        width = int(round(source.size[0] / 8.0))

        data = []
        for line in _chunked(list(source.getdata()), source.size[0]):
            row = ''.join(['0' if p else '1' for p in line])
            row = row.ljust(width * 8, '0')
            data.append(row)
        data = GRFData(width, bin=''.join(data))

        return cls(filename, data)

    def to_image(self):
        image = Image.new('1', (self.data.width, self.data.height))
        pixels = image.load()

        y = 0
        for line in self.data.bin_rows:
            x = 0
            for bit in line:
                pixels[(x,y)] = 1 - int(bit)
                x += 1
            y += 1

        return image

    @classmethod
    def from_pdf(
        cls, pdf, filename, width=288, height=432, dpi=203,
        orientation=0, font_path=None
    ):
        """
        Filename is 1-8 alphanumeric characters to identify the GRF in ZPL.

        Dimensions and DPI are for a typical 4"x6" shipping label.
        E.g. 432 points / 72 points in an inch / 203 dpi = 6 inches

        Orientation (may not work in older versions of Ghostscript):
            0 = portrait
            1 = seascape
            2 = upside down
            3 = landscape
        """

        # Most arguments below are based on what CUPS uses
        setpagedevice = [
            '/.HWMargins[0.000000 0.000000 0.000000 0.000000]',
            '/Margins[0 0]',
            '/Orientation %s' % int(orientation)
        ]
        cmd = [
            'gs',
            '-dQUIET',
            '-dPARANOIDSAFER',
            '-dNOPAUSE',
            '-dBATCH',
            '-dNOINTERPOLATE',
            '-sDEVICE=pngmono',
            '-sstdout=%stderr',
            '-sOutputFile=%stdout',
            '-dAdvanceDistance=1000',
            '-r%s' % int(dpi),
            '-dDEVICEWIDTHPOINTS=%s' % int(width),
            '-dDEVICEHEIGHTPOINTS=%s' % int(height),
            '-dPDFFitPage',
            '-c',
            '<<%s>>setpagedevice' % ' '.join(setpagedevice),
        ]

        if font_path and os.path.exists(font_path):
            cmd += ['-I' + font_path]

        cmd += [
            '-f',
            '-'
        ]

        p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate(pdf)
        if stderr:
            raise GRFException(stderr)
        return cls.from_image(stdout, filename)

    def _rotate_data(self, data, clockwise=True):
        data = [list(d) for d in data]
        if clockwise:
            data = list(zip(*data[::-1]))
        else:
            data = list(zip(*data))[::-1]
        return [''.join(d) for d in data]

    def optimise_barcodes(self, **kwargs):
        # Optimise vertical barcodes
        data = self._optimise_barcodes(self.data.bin_rows, **kwargs)

        # Optimise horizontal barcodes
        data = self._rotate_data(data, True)
        data = self._optimise_barcodes(data, **kwargs)
        data = self._rotate_data(data, False)

        self.data = GRFData(self.data.width // 8, bin=''.join(data))

    def _optimise_barcodes(
        self, data, min_bar_height=20, min_bar_count=100, max_gap_size=30,
        min_percent_white=0.2, max_percent_white=0.8, **kwargs
    ):
        """
        min_bar_height    = Minimum height of black bars in px. Set this too
                            low and it might pick up text and data matrices,
                            too high and it might pick up borders, tables, etc.
        min_bar_count     = Minimum number of parallel black bars before a
                            pattern is considered a potential barcode.
        max_gap_size      = Biggest white gap in px allowed between black bars.
                            This is only important if you have multiple
                            barcodes next to each other.
        min_percent_white = Minimum percentage of white bars between black bars.
                            This helps to ignore solid rectangles.
        max_percent_white = Maximum percentage of white bars between black bars.
                            This helps to ignore solid rectangles.
        """

        re_bars = re.compile(r'1{%s,}' % min_bar_height)

        bars = {}
        for i, line in enumerate(data):
            for match in re_bars.finditer(line):
                try:
                    bars[match.span()].append(i)
                except KeyError:
                    bars[match.span()] = [i]

        grouped_bars = []
        for span, seen_at in bars.items():
            group = []
            for coords in seen_at:
                if group and coords - group[-1] > max_gap_size:
                    grouped_bars.append((span, group))
                    group = []
                group.append(coords)
            grouped_bars.append((span, group))

        suspected_barcodes = []
        for span, seen_at in grouped_bars:
            if len(seen_at) < min_bar_count:
                continue
            pc_white = len(seen_at) / float(seen_at[-1] - seen_at[0])
            if pc_white >= min_percent_white and pc_white <= max_percent_white:
                suspected_barcodes.append((span, seen_at))

        for span, seen_at in suspected_barcodes:
            barcode = []
            for line in data[seen_at[0]:seen_at[-1]+1]:
                barcode.append(line[span[0]])
            barcode = ''.join(barcode)

            # Do the actual optimisation
            barcode = self._optimise_barcode(barcode)

            barcode = list(barcode)
            barcode.reverse()
            width = span[1] - span[0]
            for i in range(seen_at[0], seen_at[-1]+1):
                line = data[i]
                line = line[:span[0]] + (barcode.pop() * width) + line[span[1]:]
                data[i] = line

        return data

    def _optimise_barcode(self, barcode):
        if '101' not in barcode:
            # This barcode doesn't have any 1px white bars so is probably OK.
            return barcode

        barcode = barcode.replace('110', '100')

        if '101' in barcode:
            # There's still a narrow white bar, e.g. 0101
            original_length = len(barcode)
            barcode = barcode.replace('101', '1001')

            # Now we need to shorten the barcode by sacrificing from
            # wide bars. This might break the barcode.
            longest = None
            while len(barcode) > original_length:
                if not longest or longest not in barcode:
                    longest = RE_BINARY_SPLIT.findall(barcode)
                    longest = [l[0] for l in longest]
                    longest.sort(reverse=True)
                    longest = longest[0]
                barcode = barcode.replace(longest, longest[:-1], 1)

        return barcode
