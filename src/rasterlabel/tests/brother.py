from io import BytesIO

from . import TestCaseWithUtils
from ..base import RasterLabelException
from ..brother import BrotherRasterLabel, SimpleBrotherPrinter


class TestBrother(TestCaseWithUtils):
    def test_extract_printer_rasters(self):
        for file_ in ('driver-output', 'rasterlabel-output'):
            prn = self._read_file('brother/%s.prn' % file_)
            images = BrotherRasterLabel.extract_printer_rasters(
                prn
            ).to_images()

            self.assertEqual(len(images), 1)

            output = BytesIO()
            images[0].save(output, 'PNG')
            self._compare(output.getvalue(), 'brother/brother.png')

        prn = self._read_file('brother/driver-output-2pages.prn')
        images = BrotherRasterLabel.extract_printer_rasters(prn).to_images()

        self.assertEqual(len(images), 2)

        for i, image in enumerate(images, 1):
            output = BytesIO()
            image.save(output, 'PNG')
            self._compare(
                output.getvalue(), 'brother/driver-output-2pages-%i.png' % i
            )

    def test_extract_printer_rasters_bad(self):
        prn = self._read_file('brother/driver-output.prn')

        with self.assertWarnsRegex(
            Warning,
            '.*Encountered undocumented command.*'
        ):
            BrotherRasterLabel.extract_printer_rasters(
                # Turn off ignored undocumented comands
                prn,
                skip_undocumented_commands={}
            )

        with self.assertRaisesRegex(
            RasterLabelException,
            '.*Encountered non-raster mode.*'
        ):
            BrotherRasterLabel.extract_printer_rasters(
                # Break the raster mode
                prn.replace(bytes([0x61, 0x01]), bytes([0x61, 0x02]))
            )

        with self.assertRaisesRegex(
            RasterLabelException,
            '.*Number of raster lines does not match.*'
        ):
            BrotherRasterLabel.extract_printer_rasters(
                # Break the number of lines
                prn.replace(
                    bytes([0x7F, 0x00, 0x00, 0x00]),
                    bytes([0x7F, 0x00, 0x00, 0x01]),
                )
            )

    def test_print(self):
        rasters = BrotherRasterLabel.from_image(
            self._read_file('brother/brother.png')
        )

        prn = SimpleBrotherPrinter.print(
            rasters.to_printer_rasters(compression=True)
        )
        self._compare(prn, 'brother/rasterlabel-output.prn')

        images = []
        for file_ in (
            'driver-output-2pages-1',
            'driver-output-2pages-2'
        ):
            images.append(self._read_file('brother/%s.png' % file_))

        rasters = BrotherRasterLabel.from_images(images)
        prn = SimpleBrotherPrinter.print(
            rasters.to_printer_rasters(compression=True),
            auto_cut=False,
            chain_printing=True,
        )
        self._compare(prn, 'brother/rasterlabel-output-2pages.prn')

    def test_highres(self):
        prn = self._read_file('brother/driver-output-highres.prn')
        images = BrotherRasterLabel.extract_printer_rasters(prn).to_images()

        self.assertEqual(len(images), 1)

        output = BytesIO()
        images[0].save(output, 'PNG')
        self._compare(
            output.getvalue(), 'brother/driver-output-highres.png'
        )

    def test_pad_narrow(self):
        rasters = BrotherRasterLabel.from_image(
            self._read_file('brother/brother-12mm.png')
        )

        prn = SimpleBrotherPrinter.print(
            rasters.to_printer_rasters(compression=True)
        )
        self._compare(prn, 'brother/rasterlabel-output.prn')

        images = BrotherRasterLabel.extract_printer_rasters(prn).to_images()

        output = BytesIO()
        images[0].save(output, 'PNG')
        self._compare(
            output.getvalue(), 'brother/brother.png'
        )

    def test_crop_wide(self):
        rasters = BrotherRasterLabel.from_image(
            self._read_file('brother/brother-too-wide.png')
        )

        prn = SimpleBrotherPrinter.print(
            rasters.to_printer_rasters(compression=True)
        )

        self._compare(prn, 'brother/rasterlabel-output-too-wide.prn')

    def test_no_compression(self):
        rasters = BrotherRasterLabel.from_image(
            self._read_file('brother/brother-12mm.png')
        )

        rasters = rasters.to_printer_rasters(compression=False)

        with self.assertRaisesRegex(
            RasterLabelException,
            '.*Media width is required for uncompressed rasters.*'
        ):
            prn = SimpleBrotherPrinter.print(rasters)

        prn = SimpleBrotherPrinter.print(rasters, media_width=12)

        self._compare(prn, 'brother/rasterlabel-output-nocompression.prn')

        images = BrotherRasterLabel.extract_printer_rasters(prn).to_images()
        output = BytesIO()
        images[0].save(output, 'PNG')
        self._compare(
            output.getvalue(), 'brother/brother.png'
        )
