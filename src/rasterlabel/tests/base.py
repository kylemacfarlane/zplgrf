import os
from io import BytesIO

from PIL import Image

from . import TestCaseWithUtils
from ..base import RasterLabel, RasterLabelException


class TestBase(TestCaseWithUtils):
    def test_pdf_to_image(self):
        rasters = RasterLabel.from_pdf(
            self._read_file('base/pdf.pdf')
        )

        self.assertEqual(len(rasters), 1)

        output = BytesIO()
        rasters.to_images()[0].save(output, 'PNG')
        self._compare(output.getvalue(), 'base/pdf.png')

    def test_pdf_to_image_multiple_pages(self):
        rasters = RasterLabel.from_pdf(
            self._read_file('base/pdf-2pages.pdf')
        )

        self.assertEqual(len(rasters), 2)

        for i, image in enumerate(rasters.to_images(), 1):
            output = BytesIO()
            image.save(output, 'PNG')
            self._compare(output.getvalue(), 'base/pdf-2pages-%i.png' % i)

    def test_pdf_landscape(self):
        rasters = RasterLabel.from_pdf(
            self._read_file('base/pdf-landscape.pdf')
        )
        output = BytesIO()
        rasters.to_images()[0].save(output, 'PNG')
        self._compare(output.getvalue(), 'base/pdf-landscape.png')

    def test_ghostscript_center_of_pixel(self):
        rasters = RasterLabel.from_pdf(
            self._read_file('base/pdf.pdf'),
            center_of_pixel=False
        )
        output = BytesIO()
        rasters.to_images()[0].save(output, 'PNG')
        self._compare(output.getvalue(), 'base/pdf-centerofpixel-false.png')

        # Perhaps we should install a copy of GS 9.22-9.26 instead of
        # doing this. However doing it like this does allow us to test error
        # handling.
        with self.assertRaisesRegex(
            RasterLabelException,
            '.*\/undefined in \.setfilladjust.*'
        ):
            rasters = RasterLabel.from_pdf(
                self._read_file('base/pdf.pdf'),
                center_of_pixel_922_926=True
            )

    def test_pdf_to_image_using_bindings(self):
        rasters = RasterLabel.from_pdf(
            self._read_file('base/pdf.pdf'),
            use_bindings=True
        )

        self.assertEqual(len(rasters), 1)

        output = BytesIO()
        rasters.to_images()[0].save(output, 'PNG')
        self._compare(output.getvalue(), 'base/pdf.png')

        # Test error handling but it doesn't seem like the bindings return
        # the full error message.
        with self.assertRaisesRegex(RasterLabelException, '.*Fatal.*'):
            rasters = RasterLabel.from_pdf(
                self._read_file('base/pdf.pdf'),
                use_bindings=True,
                center_of_pixel_922_926=True
            )

    def test_ghostscript_font_path(self):
        # Doesn't actually test if GS uses the font, only that we add the path
        # to the command
        rasters = RasterLabel.from_pdf(
            self._read_file('base/pdf.pdf'),
            font_path=os.path.join(os.path.dirname(__file__), 'input')
        )

        output = BytesIO()
        rasters.to_images()[0].save(output, 'PNG')
        self._compare(output.getvalue(), 'base/pdf.png')

    def test_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            RasterLabel.extract_printer_rasters('')

        rasters = RasterLabel.from_images(
            [self._read_file('base/pdf.png')]
        )

        with self.assertRaises(NotImplementedError):
            rasters.to_printer_rasters()

        with self.assertRaises(NotImplementedError):
            rasters[0].to_printer_raster()

    def test_from_images(self):
        raster1 = RasterLabel.from_images(
            [self._read_file('base/pdf.png')]
        )[0]

        raster2 = RasterLabel.from_images(
            [Image.open(BytesIO(self._read_file('base/pdf.png')))]
        )[0]

        raster3 = RasterLabel.from_image(
            Image.open(BytesIO(self._read_file('base/pdf.png')))
        )[0]

        for raster in (raster1, raster2, raster3):
            output = BytesIO()
            raster.to_image().save(output, 'PNG')
            self._compare(output.getvalue(), 'base/pdf.png')

    def test_rasterlabel(self):
        raster1 = RasterLabel.from_images([self._read_file('base/pdf.png')])[0]

        self.assertEqual(raster1.filesize, 124236)
        self.assertEqual(raster1.width, 816)
        self.assertEqual(raster1.height, 1218)
        self.assertEqual(len(raster1.bytes), 124236)
        self.assertEqual(len(list(raster1.bytes_rows)), 1218)

        raster2 = RasterLabel.from_bytes(raster1.bytes, raster1.width // 8)

        for attr in ('filesize', 'width', 'height', 'bytes'):
            self.assertEqual(
                getattr(raster1, attr), getattr(raster2, attr), attr
            )

        self.assertEqual(
            list(raster1.bytes_rows),
            list(raster2.bytes_rows)
        )

    def test_rasterlabelcollection(self):
        rasters = RasterLabel.from_pdf(
            self._read_file('base/pdf-2pages.pdf')
        )

        # Test __len__
        self.assertEqual(len(rasters), 2)

        for i, raster in enumerate(rasters):
            # Test __iter__
            self.assertEqual(raster, rasters[i])

        # Test __gettitem__
        raster = rasters[0]

    def test_rotate(self):
        rasters = RasterLabel.from_pdf(
            self._read_file('base/pdf-2pages.pdf')
        )
        rasters.rotate()

        for i, image in enumerate(rasters.to_images(), 1):
            output = BytesIO()
            image.save(output, 'PNG')
            self._compare(
                output.getvalue(), 'base/pdf-2pages-rotated-%i.png' % i
            )
