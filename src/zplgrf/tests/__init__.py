import os
import unittest
from io import BytesIO

from zplgrf import GRF


class TestStringMethods(unittest.TestCase):
    def _read_file(self, file_):
        mode = 'r' if file_.endswith('.zpl') else 'rb'
        input_dir = os.path.join(os.path.dirname(__file__), 'input')
        with open(os.path.join(input_dir, file_), mode) as file_:
            return file_.read()

    def _compare(self, a, b):
        self.assertEqual(a, self._read_file(b))

    def test_pdf_to_image(self):
        grf = GRF.from_pdf(self._read_file('pdf.pdf'), 'TEST')[0]

        output = BytesIO()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-image.png')

        output = BytesIO()
        grf.optimise_barcodes()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-optimised-image.png')

    def test_pdf_to_image_multiple_pages(self):
        grfs = GRF.from_pdf(self._read_file('pdf-2pages.pdf'), 'TEST')

        self.assertEqual(len(grfs), 2)

        for i, grf in enumerate(grfs):
            output = BytesIO()
            grf.to_image().save(output, 'PNG')
            self._compare(output.getvalue(), 'pdf-2pages-%i.png' % i)

    def test_pdf_landscape(self):
        grf = GRF.from_pdf(self._read_file('pdf-landscape.pdf'), 'TEST')[0]
        output = BytesIO()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-landscape.png')

    def test_image_to_zpl(self):
        grf = GRF.from_image(self._read_file('pdf-image.png'), 'TEST')
        grf.optimise_barcodes()
        self._compare(grf.to_zpl(copies=2), 'image-optimised-zb64-copies2.zpl')

    def test_zpl_to_zpl(self):
        zpl = GRF.replace_grfs_in_zpl(self._read_file('pdf-asciihex.zpl'))
        self._compare(zpl, 'asciihex-optimised-zb64.zpl')

        grf = GRF.from_zpl(self._read_file('pdf-asciihex.zpl'))[0]
        grf.optimise_barcodes()
        self._compare(grf.to_zpl(compression=1), 'pdf-optimised-b64.zpl')
        self._compare(grf.to_zpl(compression=2), 'pdf-optimised-asciihex.zpl')
        self._compare(grf.to_zpl(compression=3), 'pdf-optimised-zb64.zpl')

    def test_zpl_to_image(self):
        grf = GRF.from_zpl(self._read_file('pdf-asciihex.zpl'))[0]
        output = BytesIO()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-image.png')

        output = BytesIO()
        grf.optimise_barcodes()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-optimised-image.png')

    def test_ghostscript_center_of_pixel(self):
        grf = GRF.from_pdf(
            self._read_file('pdf.pdf'), 'TEST', center_of_pixel=True
        )[0]
        output = BytesIO()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-image-centerofpixel.png')

    def test_pdf_to_image_using_bindings(self):
        grfs = GRF.from_pdf(
            self._read_file('pdf-2pages.pdf'), 'TEST', use_bindings=True
        )

        self.assertEqual(len(grfs), 2)

        for i, grf in enumerate(grfs):
            output = BytesIO()
            grf.to_image().save(output, 'PNG')
            self._compare(output.getvalue(), 'pdf-2pages-%i.png' % i)

        grf = GRF.from_pdf(
            self._read_file('pdf.pdf'), 'TEST', center_of_pixel=True,
            use_bindings=True
        )[0]
        output = BytesIO()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-image-centerofpixel.png')

    def test_from_b64_zpl(self):
        grf = GRF.from_zpl(self._read_file('pdf-optimised-zb64.zpl'))[0]
        self._compare(grf.to_zpl(compression=2), 'pdf-optimised-asciihex.zpl')
        output = BytesIO()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-optimised-image.png')
