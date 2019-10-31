"""
Tests for ocw_data_parser
"""
import json
import unittest
import os
import shutil

from ocw_data_parser.ocw_data_parser import OCWParser
from ocw_data_parser.utils import *


class TestOCWParser(unittest.TestCase):
    """
    Tests for OCW Parser
    """
    ocw_parser = None
    course_id = None

    def set_up(self, extract_media_locally=False, extract_foreign_media_locally=False, generate_static_site=False, setup_s3_uploading=False):
        self.ocw_parser = OCWParser(course_dir="ocw_data_parser/test_json/course_dir",
                                    destination_dir="ocw_data_parser/test_json/destination_dir",
                                    static_prefix="static_files/")
        if extract_media_locally:
            self.ocw_parser.extract_media_locally()
        if extract_foreign_media_locally:
            self.ocw_parser.extract_foreign_media_locally()
        if generate_static_site:
            self.ocw_parser.generate_static_site()
        if setup_s3_uploading:
            self.ocw_parser.setup_s3_uploading(
                s3_bucket_name = "bucket_name",
                s3_bucket_access_key = "bucket_access_key",
                s3_bucket_secret_access_key = "bucket_secret_access_key",
                folder = "target_folder"
            )
        self.course_id = self.ocw_parser.master_json["short_url"]
    
    def tear_down(self):
        destination_dir = "ocw_data_parser/test_json/destination_dir"
        self.ocw_parser = None
        if os.path.isdir(destination_dir):
            shutil.rmtree(destination_dir)
        self.course_id = None

    # utils.py

    def test_update_local_file_location(self):
        self.set_up(extract_media_locally=True)
        if len(self.ocw_parser.master_json["course_files"]) > 0:
            test_file = self.ocw_parser.master_json["course_files"][0]
            original_location = test_file["file_location"]
            update_file_location(self.ocw_parser.master_json, 'test_location', obj_uid=test_file["uid"])
            self.assertNotEqual(original_location, self.ocw_parser.master_json["course_files"][0]["file_location"])
            self.tear_down()
        else:
            self.tear_down()
            self.fail("test course has no local media to test")

    def test_update_foreign_file_location(self):
        self.set_up(extract_foreign_media_locally=True)
        if len(self.ocw_parser.master_json["course_foreign_files"]) > 0:
            test_file = self.ocw_parser.master_json["course_foreign_files"][0]
            original_location = test_file["file_location"]
            original_filename = test_file["link"].split("/")[-1]
            update_file_location(self.ocw_parser.master_json, 'test_location/' + original_filename)
            self.assertNotEqual(original_location, self.ocw_parser.master_json["course_foreign_files"][0]["file_location"])
            self.tear_down()
        else:
            self.tear_down()
            self.fail("test course has no foreign media to test")

    # ocw_data_parser.py

    def test_no_params(self):
        """
        Test that an OCWParser with no params raises an exception
        """
        with self.assertRaises(Exception):
            OCWParser()

    def test_get_master_json(self):
        """
        Test that getting the master JSON is not None or empty and doesn't throw an exception
        """
        self.set_up()
        try:
            self.assertTrue(self.ocw_parser.get_master_json())
        except:
            self.fail("get_master_json raised an exception")
        self.tear_down()

    def test_set_s3_bucket_name(self):
        self.set_up(setup_s3_uploading=True)
        self.assertEqual("bucket_name", self.ocw_parser.s3_bucket_name)
        self.tear_down()

    def test_set_s3_access_key(self):
        self.set_up(setup_s3_uploading=True)
        self.assertEqual("bucket_access_key", self.ocw_parser.s3_bucket_access_key)
        self.tear_down()

    def test_set_s3_secret_access_key(self):
        self.set_up(setup_s3_uploading=True)
        self.assertEqual("bucket_secret_access_key", self.ocw_parser.s3_bucket_secret_access_key)
        self.tear_down()

    def test_set_s3_target_folder(self):
        self.set_up(setup_s3_uploading=True)
        self.assertEqual("target_folder", self.ocw_parser.s3_target_folder)
        self.tear_down()

    

    def test_uid(self):
        """
        Test that the uid property of the master JSON matches the uid of the course site root
        """
        self.set_up(generate_static_site=True)
        with open('ocw_data_parser/test_json/course_dir/jsons/1.json', 'r') as first_json:
            first_json_data = json.loads(first_json.read())
            with open('ocw_data_parser/test_json/destination_dir/{}/master/master.json'.format(self.course_id), 'r') as master_json:
                master_json_data = json.loads(master_json.read())
                self.assertEqual(first_json_data["_uid"], master_json_data["uid"])
        self.tear_down()

if __name__ == '__main__':
    unittest.main()