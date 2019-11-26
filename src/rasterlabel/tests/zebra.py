from io import BytesIO

from . import TestCaseWithUtils
from ..base import RasterLabelException
from ..zebra import SimpleZebraPrinter, ZebraRasterLabel


class TestZebra(TestCaseWithUtils):
    def test_zb64(self):
        rasters = ZebraRasterLabel.from_pdf(
            self._read_file('base/pdf.pdf')
        )
        self._compare(
            rasters.to_printer_rasters(compression=3),
            'zebra/zb64.json'
        )

    def test_asciihex(self):
        rasters = ZebraRasterLabel.from_pdf(
            self._read_file('base/pdf.pdf')
        )
        self._compare(
            rasters.to_printer_rasters(compression=2),
            'zebra/asciihex.json'
        )

    def test_asciihex_long_repeat(self):
        rasters = ZebraRasterLabel.from_pdf(
            self._read_file('zebra/asciihex-long-repeat.pdf'),
            height=288 * 2,
            width=432 * 2
        )
        rasters = rasters.to_printer_rasters(compression=2)
        self._compare(rasters, 'zebra/asciihex-long-repeat.json')

        zpl = SimpleZebraPrinter.print(rasters)
        images = ZebraRasterLabel.extract_printer_rasters(zpl).to_images()
        output = BytesIO()
        images[0].save(output, 'PNG')
        self._compare(output.getvalue(), 'zebra/asciihex-long-repeat.png')

    def test_b64(self):
        rasters = ZebraRasterLabel.from_pdf(
            self._read_file('base/pdf.pdf')
        )
        self._compare(
            rasters.to_printer_rasters(compression=1),
            'zebra/b64.json'
        )

    def test_print(self):
        rasters = ZebraRasterLabel.from_pdf(
            self._read_file('base/pdf.pdf')
        )

        zpl = SimpleZebraPrinter.print(
            rasters.to_printer_rasters(compression=3)
        )
        self._compare(zpl, 'zebra/zb64.zpl')

        zpl = SimpleZebraPrinter.print(
            rasters.to_printer_rasters(compression=2)
        )
        self._compare(zpl, 'zebra/asciihex.zpl')

        zpl = SimpleZebraPrinter.print(
            rasters.to_printer_rasters(compression=1)
        )
        self._compare(zpl, 'zebra/b64.zpl')

        rasters = ZebraRasterLabel.from_pdf(
            self._read_file('base/pdf.pdf'),
            center_of_pixel=False
        )
        zpl = SimpleZebraPrinter.print(
            rasters.to_printer_rasters(compression=3)
        )
        self._compare(zpl, 'zebra/zb64-centerofpixel-false.zpl')

        rasters = ZebraRasterLabel.from_pdf(
            self._read_file('base/pdf-2pages.pdf')
        )
        zpl = SimpleZebraPrinter.print(
            rasters.to_printer_rasters(compression=3)
        )
        self._compare(zpl, 'zebra/pdf-2pages.zpl')

    def test_extract_printer_rasters(self):
        for file_ in ('zb64', 'asciihex', 'b64', 'dg', 'dy', 'gf'):
            zpl = self._read_file('zebra/%s.zpl' % file_, False)
            images = ZebraRasterLabel.extract_printer_rasters(zpl)
            images = images.to_images()

            self.assertEqual(len(images), 1)

            output = BytesIO()
            images[0].save(output, 'PNG')
            self._compare(output.getvalue(), 'base/pdf.png')

        zpl = self._read_file('zebra/pdf-2pages.zpl', False)
        images = ZebraRasterLabel.extract_printer_rasters(zpl).to_images()

        self.assertEqual(len(images), 2)

        for i, image in enumerate(images, 1):
            output = BytesIO()
            image.save(output, 'PNG')
            self._compare(output.getvalue(), 'base/pdf-2pages-%i.png' % i)

    def test_extract_printer_rasters_bad(self):
        zpl = self._read_file('zebra/zb64.zpl', False)

        with self.assertRaisesRegex(
            RasterLabelException,
            '.*Bad CRC.*'
        ):
            ZebraRasterLabel.extract_printer_rasters(
                # Break the CRC
                zpl.replace(':E78D^', ':ABCD^')
            )

        with self.assertRaisesRegex(
            RasterLabelException,
            '.*Bad file size.*'
        ):
            ZebraRasterLabel.extract_printer_rasters(
                # Break the filesize
                zpl.replace(',124236,', ',124235,')
            )

        zpl = self._read_file('zebra/dy.zpl', False)
        rasters = ZebraRasterLabel.extract_printer_rasters(
            # Change the format to a font
            zpl.replace(',G,', ',E,')
        )
        self.assertEqual(len(rasters), 0)
        with self.assertRaisesRegex(
            RasterLabelException,
            '.*Unimplemented graphic format.*'
        ):
            ZebraRasterLabel.extract_printer_rasters(
                # Change the format to an unsupported raster
                zpl.replace(',G,', ',B,')
            )

        zpl = self._read_file('zebra/gf.zpl', False)
        with self.assertRaisesRegex(
            RasterLabelException,
            '.*Unimplemented compression.*'
        ):
            ZebraRasterLabel.extract_printer_rasters(
                # Change the compression
                zpl.replace('^GFA', '^GFB')
            )
