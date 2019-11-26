import json
import os
import unittest


class TestCaseWithUtils(unittest.TestCase):
    def _read_file(self, file_, binary=True):
        if binary:
            mode = 'rb'
        else:
            mode = 'r'
        input_dir = os.path.join(os.path.dirname(__file__), 'input')
        with open(os.path.join(input_dir, file_), mode) as file_:
            return file_.read()

    def _compare(self, a, b):
        if b.endswith('.json'):
            a = json.dumps(a, sort_keys=True)
        self.assertEqual(
            a,
            self._read_file(b, binary=isinstance(a, bytes))
        )
