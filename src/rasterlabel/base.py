import math
import os
import tempfile
from io import BytesIO

from PIL import Image


class RasterLabelException(Exception):
    pass


class RasterLabelCollection:
    def __init__(self, rasters):
        self.rasters = rasters

    def __getitem__(self, i):
        return self.rasters[i]

    def __iter__(self):
        yield from self.rasters

    def __len__(self):
        return len(self.rasters)

    def to_printer_rasters(self, *args, **kwargs):
        printable = []

        for raster in self.rasters:
            printable.append(raster.to_printer_raster(*args, **kwargs))

        return printable

    def to_images(self):
        images = []

        for raster in self.rasters:
            images.append(raster.to_image())

        return images

    def rotate(self, angle=180):
        for r in self.rasters:
            r.rotate(angle=180)
        self.rasters.reverse()


class RasterLabel:
    def __init__(self, image):
        self._image = image
        self._bytes_cache = None

    @property
    def height(self):
        return self._image.size[1]

    @property
    def width(self):
        return self._image.size[0]

    @property
    def bytes(self):
        if self._bytes_cache is None:
            self._bytes_cache = self._image.tobytes('raw', '1;I')
        return self._bytes_cache

    @property
    def filesize(self):
        return len(self.bytes)

    @property
    def bytes_rows(self):
        chunk_size = self.width // 8
        for i in range(0, len(self.bytes), chunk_size):
            yield self.bytes[i:i+chunk_size]

    def to_image(self):
        return self._image

    def rotate(self, angle=180):
        self._image = self._image.rotate(angle)
        self._bytes_cache = None

    def to_printer_raster(self, *args, **kwargs):
        raise NotImplementedError()

    @classmethod
    def extract_printer_rasters(cls, data):
        raise NotImplementedError()

    @classmethod
    def from_bytes(cls, bytes, bytes_per_row):
        width = bytes_per_row * 8
        height = len(bytes) // bytes_per_row
        return cls(Image.frombytes(
            '1', (width, height), bytes, 'raw', '1;I'
        ))

    @classmethod
    def from_images(cls, images):
        rasters = []

        for image in images:
            if not isinstance(image, Image.Image):
                image = Image.open(BytesIO(image))

            # Convert to 1-bit black and white
            image = image.convert('1')

            # Pad to a width that fits evenly into 8 bits
            padded_width = int(math.ceil(image.size[0] / 8.0)) * 8
            if image.size[0] < padded_width:
                padded = Image.new('1', (padded_width, image.size[1]), 255)
                padded.paste(image, (0, 0))
                image = padded

            rasters.append(cls(image))

        return RasterLabelCollection(rasters)

    @classmethod
    def from_image(cls, image):
        return cls.from_images([image])

    @classmethod
    def from_pdf(
        cls, pdf, width=288, height=432, dpi=203, font_path=None,
        center_of_pixel=True, center_of_pixel_922_926=False, use_bindings=False
    ):
        """
        Dimensions and DPI are for a typical 4"x6" shipping label.
        E.g. 432 points / 72 points in an inch / 203 dpi = 6 inches

        Using center of pixel will improve barcode quality but may decrease
        the quality of some text.

        use_bindings=False:
            - Uses subprocess.Popen
            - Forks so there is a memory spike
            - Easier to setup - only needs the gs binary

        use_bindings=True:
            - Uses python-ghostscript
            - Doesn't fork so should use less memory
            - python-ghostscript is a bit buggy
            - May be harder to setup - even if you have updated the gs binary
              there may stil be old libgs* files on your system
        """

        # Most ghostscript arguments below are based on what CUPS uses (I think
        # I changed some stuff for better autoscaling which is handled higher
        # up in CUPS)

        setpagedevice = [
            '/.HWMargins[0.000000 0.000000 0.000000 0.000000]',
            '/Margins[0 0]'
        ]

        cmd = [
            'gs',
            '-dQUIET',
            '-dPARANOIDSAFER',
            '-dNOPAUSE',
            '-dBATCH',
            '-dNOINTERPOLATE',
            '-sDEVICE=pngmono',
            '-dAdvanceDistance=1000',
            '-r%s' % int(dpi),
            '-dDEVICEWIDTHPOINTS=%s' % int(width),
            '-dDEVICEHEIGHTPOINTS=%s' % int(height),
            '-dFIXEDMEDIA',
            '-dPDFFitPage',
            '-c',
            '<<%s>>setpagedevice' % ' '.join(setpagedevice)
        ]

        if center_of_pixel:
            # <= 9.21 = "0 .setfilladjust" or "0 0 .setfilladjust2"
            # 9.22-9.26 = only "0 .setfilladjust"
            # >= 9.27 = only "0 0 .setfilladjust2"
            if center_of_pixel_922_926:
                cmd += ['0 .setfilladjust']
            else:
                cmd += ['0 0 .setfilladjust2']

        if font_path and os.path.exists(font_path):
            cmd += ['-I' + font_path]

        if use_bindings:
            import ghostscript
            # python-ghostscript doesn't like reading/writing from
            # stdin/stdout so we need to use temp files
            with tempfile.NamedTemporaryFile() as in_file, \
                 tempfile.NamedTemporaryFile() as out_file:  # noqa

                in_file.write(pdf)
                in_file.flush()

                # Ghostscript seems to be sensitive to argument order
                cmd[13:13] += [
                    '-sOutputFile=%s' % out_file.name
                ]
                cmd += [
                    '-f', in_file.name
                ]

                try:
                    ghostscript.Ghostscript(*[c.encode('ascii') for c in cmd])
                except Exception as e:
                    raise RasterLabelException(e)

                pngs = out_file.read()
        else:
            from subprocess import PIPE, Popen
            # Ghostscript seems to be sensitive to argument order
            cmd[13:13] += [
                '-sstdout=%stderr',
                '-sOutputFile=%stdout',
            ]
            cmd += [
                '-f', '-'
            ]
            p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
            pngs, stderr = p.communicate(pdf)
            if stderr:
                raise RasterLabelException(stderr)

        # This is what PIL uses to identify PNGs
        png_start = b'\211PNG\r\n\032\n'

        images = [png_start + png for png in pngs.split(png_start)[1:]]

        return cls.from_images(images)
