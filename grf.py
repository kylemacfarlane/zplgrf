#!/usr/bin/env python


import base64
from bitstring import BitArray
from io import BytesIO
import os
from subprocess import Popen, PIPE
import re
import sys
import zlib


RE_COMPRESSED = re.compile(r'[G-Zg-z]+.')
RE_UNCOMPRESSED = re.compile(r'((.)\2{1,})')
RE_BINARY_SPLIT = re.compile(r'((.)\2*)')


class GRFException(Exception):
    pass


class GRF(object):
    def __init__(self, filename, width, data):
        if not filename or not filename.isalnum() or len(filename) > 8:
            raise GRFException('Filename must be 1-8 alphanumeric characters')
        self.filename = filename.upper()
        self.filesize = len(data.bytes)
        self.width = width
        self.height = len(list(self._chunked(data, width)))
        self.data = data

    @staticmethod
    def _chunked(value, n):
        for i in range(0, len(value), n):
            yield value[i:i+n]

    @staticmethod
    def _calc_crc(data):
        from PyCRC.CRCCCITT import CRCCCITT
        if not isinstance(data, bytes):
            data = data.encode('ascii') # Python 2 compatibility
        return format(CRCCCITT().calculate(data), 'X')

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
            data = BitArray(bytes=data)
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
                    rows.append(row)
                    row = ''
            data = BitArray(hex=''.join(rows))

        if len(data.bytes) != filesize:
            raise GRFException('Bad file size')

        return cls(filename, width * 8, data)

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

            for line in self._chunked(self.data.hex, self.width // 4):
                line = line.upper()
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
            self.filesize,
            self.width / 8,
            data
        )

        return zpl

    def to_zpl(self, **kwargs):
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
            '^XZ', # End Label Format
            '^IDR:%s.GRF' % self.filename # Delete image from printer
        ]
        return ''.join(zpl)

    @classmethod
    def from_image(cls, png, filename):
        """
        Filename is 1-8 alphanumeric characters to identify the GRF in ZPL.
        """

        from PIL import Image

        source = Image.open(BytesIO(png))
        source = source.convert('1')
        width = round(source.size[0] / 8.0)

        data = []
        for line in cls._chunked(list(source.getdata()), source.size[0]):
            row = ''.join(['0' if p else '1' for p in line])
            row = row.ljust(width, '0')
            data.append(row)
        data = BitArray(bin=''.join(data))

        return cls(filename, width * 8, data)

    def to_image(self):
        from PIL import Image

        image = Image.new('1', (self.width, self.height))
        pixels = image.load()

        y = 0
        for line in self._chunked(self.data.bin, self.width):
            x = 0
            for bit in line:
                pixels[(x,y)] = 1 - int(bit)
                x += 1
            y += 1

        return image

    @classmethod
    def from_pdf(
        cls, pdf, filename,
        width=288, height=432,
        width_dpi=203, height_dpi=203,
        orientation=0
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
            '-r%sx%s' % (int(height_dpi), int(width_dpi)),
            '-dDEVICEWIDTHPOINTS=%s' % int(width),
            '-dDEVICEHEIGHTPOINTS=%s' % int(height),
            '-dPDFFitPage',
            '-c',
            '<<%s>>setpagedevice' % ' '.join(setpagedevice),
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
        data = list(self._chunked(self.data.bin, self.width))

        # Optimise vertical barcodes
        data = self._optimise_barcodes(data, **kwargs)

        # Optimise horizontal barcodes
        data = self._rotate_data(data, True)
        data = self._optimise_barcodes(data, **kwargs)
        data = self._rotate_data(data, False)

        self.data = BitArray(bin=''.join(data))

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

            if '101' in barcode:
                # This barcode has 1px wide white bars which need widening.
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

            barcode = list(barcode)
            barcode.reverse()
            width = span[1] - span[0]
            for i in range(seen_at[0], seen_at[-1]+1):
                line = data[i]
                line = line[:span[0]] + (barcode.pop() * width) + line[span[1]:]
                data[i] = line

        return data


if __name__ == '__main__':
    cmd = os.path.join(os.path.dirname(sys.argv[0]), 'rastertolabel')
    p = Popen([cmd] + sys.argv[1:], stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdin = getattr(sys.stdin, 'buffer', sys.stdin) # Python 2 compatibility
    stdout, stderr = p.communicate(stdin.read())
    sys.stdout.write(GRF.replace_grfs_in_zpl(stdout.decode('ascii')))
