from io import BytesIO
import os
import unittest
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
        grf = GRF.from_pdf(self._read_file('pdf.pdf'), 'TEST')

        output = BytesIO()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-image.png')

        output = BytesIO()
        grf.optimise_barcodes()
        grf.to_image().save(output, 'PNG')
        self._compare(output.getvalue(), 'pdf-optimised-image.png')

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
