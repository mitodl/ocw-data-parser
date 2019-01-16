"""
Tests for ocw_data_parser
"""
import json
import unittest

from ocw_data_parser import OCWParser


class TestOCWParser(unittest.TestCase):
    """
    Tests for OCW Parser
    """

    def test_no_params(self):
        """
        Test that an OCWParser with no params raises an exception
        """
        with self.assertRaises(Exception):
            OCWParser()

    def test_ocw_parser_output(self):
        """
        Test that OCWParser handles downloaded json
        """
        ocw_parser = OCWParser(course_dir="ocw_data_parser/test_json/course_dir",
                               destination_dir="ocw_data_parser/test_json/destination_dir")
        with open('ocw_data_parser/test_json/master_json.json', 'r') as master_json:
            master_json_data = json.loads(master_json.read())
            self.assertEqual(master_json_data, ocw_parser.master_json)
