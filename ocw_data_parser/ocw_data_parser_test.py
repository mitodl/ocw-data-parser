"""
Tests for ocw_data_parser
"""
import json
import unittest
import os
import shutil

from ocw_data_parser import OCWParser


class TestOCWParser(unittest.TestCase):
    """
    Tests for OCW Parser
    """
    ocw_parser = None
    course_id = None

    def set_up(self):
        self.ocw_parser = OCWParser(course_dir="ocw_data_parser/test_json/course_dir",
                                    destination_dir="ocw_data_parser/test_json/destination_dir",
                                    static_prefix="static_files/")
        self.ocw_parser.generate_static_site()
        self.course_id = self.ocw_parser.master_json["short_url"]
    
    def tear_down(self):
        destination_dir = "ocw_data_parser/test_json/destination_dir"
        self.ocw_parser = None
        if os.path.isdir(destination_dir):
            shutil.rmtree(destination_dir)
        self.course_id = None

    def test_no_params(self):
        """
        Test that an OCWParser with no params raises an exception
        """
        with self.assertRaises(Exception):
            OCWParser()

    def test_uid(self):
        """
        Test that the uid property of the master JSON matches the uid of the course site root
        """
        self.set_up()
        with open('ocw_data_parser/test_json/course_dir/jsons/1.json', 'r') as first_json:
            first_json_data = json.loads(first_json.read())
            with open('ocw_data_parser/test_json/destination_dir/{}/master/master.json'.format(self.course_id), 'r') as master_json:
                master_json_data = json.loads(master_json.read())
                self.assertEqual(first_json_data["_uid"], master_json_data["uid"])
        self.tear_down()

if __name__ == '__main__':
    unittest.main()