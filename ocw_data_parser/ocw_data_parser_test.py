"""
Tests for ocw_data_parser
"""
import json
import unittest
import os
import shutil
import responses
import boto3
from moto import mock_s3
from ocw_data_parser.ocw_data_parser import CustomHTMLParser, OCWParser
from ocw_data_parser.utils import update_file_location, get_binary_data, is_json, get_correct_path, load_json_file, print_error, print_success, safe_get, find_all_values_for_key


class TestOCWParser(unittest.TestCase):
    """
    Tests for OCW Parser
    """
    ocw_parser = None
    course_id = None

    @mock_s3
    def set_up(self, extract_media_locally=False, extract_foreign_media_locally=False, generate_static_site=False, setup_s3_uploading=False):
        """
        Instantiace an OCWParser object and run functions depending on args passed in
        """
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
                s3_bucket_name = "testing",
                s3_bucket_access_key = "testing",
                s3_bucket_secret_access_key = "testing",
                folder = "testing"
            )
            conn = boto3.client('s3',
                aws_access_key_id=self.ocw_parser.s3_bucket_access_key, 
                aws_secret_access_key=self.ocw_parser.s3_bucket_secret_access_key)
            conn.create_bucket(Bucket=self.ocw_parser.s3_bucket_name)
            responses.add_passthru("https://")
            responses.add_passthru("http://")
            s3 = boto3.resource('s3',
                aws_access_key_id=self.ocw_parser.s3_bucket_access_key, 
                aws_secret_access_key=self.ocw_parser.s3_bucket_secret_access_key)
            self.s3_bucket = s3.Bucket(name=self.ocw_parser.s3_bucket_name)
        self.course_id = self.ocw_parser.master_json["short_url"]
    
    def tear_down(self):
        """
        Remove any generated files and null out local variables
        """
        destination_dir = "ocw_data_parser/test_json/destination_dir"
        self.ocw_parser = None
        if os.path.isdir(destination_dir):
            shutil.rmtree(destination_dir)
        self.course_id = None

    # utils.py

    def test_update_local_file_location(self):
        """
        Extract local course media, update the location of one of the files 
        and then assert that the location has indeed changed
        """
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
        """
        Extract foreign course media, update the location of one of the files 
        and then assert that the location has indeed changed
        """
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

    def test_get_binary_data_none(self):
        """
        Find the first file without a datafield property and attempt to get the binary data from it
        """
        self.set_up()
        if len(self.ocw_parser.master_json["course_files"]) > 0:
            for media in self.ocw_parser.master_json["course_files"]:
                if "_datafield_image" not in media and "_datafield_file" not in media:
                    data = get_binary_data(media)
                    self.assertIsNone(data)
        else:
            self.tear_down()
            self.fail("test course has no local media to test")

    def test_get_correct_path_none(self):
        """
        Test passing in invalid data to get_correct_path
        """
        get_correct_path(None)
        
    def test_load_invalid_json_file(self):
        """
        Test passing in an invalid JSON file (this one)
        """
        self.assertIsNone(load_json_file('ocw_data_parser/ocw_data_parser_test.py'))

    def test_print_error(self):
        """
        Test printing an error doesn't throw an exception
        """
        try:
            print_error("Error!")
        except:
            self.fail("print_error raised an exception")

    def test_print_success(self):
        """
        Test that printing a success message doesn't throw an exception
        """
        try:
            print_success("Success!")
        except:
            self.fail("print_success raised an exception")

    def test_safe_get_invalid_value(self):
        """
        Test trying to get a value from a dict that doesn't exist
        """
        test_dict = {
            "value_one": "1",
            "value_two": "2",
            "actual_file_name": 'test'
        }
        self.assertIsNone(safe_get(test_dict, "value_three", print_error_message=True))

    # ocw_data_parser.py

    def test_no_params(self):
        """
        Test that an OCWParser with no params raises an exception
        """
        with self.assertRaises(Exception):
            OCWParser()

    def test_html_parser_output_list(self):
        """
        Test passing in an output_list to the CustomHTMLParser
        """
        output_list = ['test']
        parser = CustomHTMLParser(output_list=output_list)
        self.assertEqual('test', parser.output_list[0])

    def test_parser_loaded_jsons(self):
        """
        Test instantiating a parser with preloaded jsons
        """
        self.set_up()
        try:
            OCWParser(loaded_jsons=self.ocw_parser.jsons)
            self.tear_down()
        except:
            self.tear_down()
            self.fail("instantiating parser with preloaded jsons failed")

    def test_generate_master_json_none_source(self):
        """
        Make sure that running generate_master_json doesn't throw an error after nulling 
        out the parser's source jsons
        """
        self.set_up()
        self.ocw_parser.jsons = None
        self.ocw_parser.generate_master_json()
        self.assertIsNotNone(self.ocw_parser.jsons)
        self.tear_down()

    def test_generate_master_json_none_course_image_uid(self):
        """
        Make sure course_image_uid is regenerated by generate_master_json after it's nulled out
        """
        self.set_up()
        self.ocw_parser.course_image_uid = None
        self.ocw_parser.generate_master_json()
        self.assertIsNotNone(self.ocw_parser.course_image_uid)
        self.tear_down()

    def test_load_raw_jsons_invalid_file(self):
        """
        Add a json file with invalid content to the course_dir and make sure it generates an exception
        """
        with open("ocw_data_parser/test_json/course_dir/jsons/test.json", "w") as f:
            f.write("")
        with self.assertRaises(Exception):
            self.set_up(generate_static_site=True)
        os.remove("ocw_data_parser/test_json/course_dir/jsons/test.json")
        self.tear_down()

    @mock_s3
    def test_upload_all_data_to_s3(self):
        """
        Use moto (mock boto) to test s3 uploading
        """
        self.set_up(setup_s3_uploading=True)
        self.ocw_parser.upload_all_media_to_s3(upload_master_json=True)
        course_image_key = None
        for bucket_item in self.s3_bucket.objects.filter(Prefix=self.ocw_parser.s3_target_folder):
            if bucket_item.key in self.ocw_parser.course_image_s3_link:
                course_image_key = bucket_item.key
        self.assertIsNotNone(course_image_key)
        self.tear_down()

    @mock_s3
    def test_upload_course_image(self):
        """
        Use moto (mock boto) to test s3 uploading
        """
        self.set_up(setup_s3_uploading=True)
        self.ocw_parser.upload_course_image()
        course_image_key = None
        for bucket_item in self.s3_bucket.objects.filter(Prefix=self.ocw_parser.s3_target_folder):
            if bucket_item.key in self.ocw_parser.course_image_s3_link:
                course_image_key = bucket_item.key
        self.assertIsNotNone(course_image_key)
        self.tear_down()

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
        """
        Test setting the s3 bucket name
        """
        self.set_up(setup_s3_uploading=True)
        self.assertEqual("testing", self.ocw_parser.s3_bucket_name)
        self.tear_down()

    def test_set_s3_access_key(self):
        """
        Test setting the s3 access key
        """
        self.set_up(setup_s3_uploading=True)
        self.assertEqual("testing", self.ocw_parser.s3_bucket_access_key)
        self.tear_down()

    def test_set_s3_secret_access_key(self):
        """
        Test setting the s3 secret access key
        """
        self.set_up(setup_s3_uploading=True)
        self.assertEqual("testing", self.ocw_parser.s3_bucket_secret_access_key)
        self.tear_down()

    def test_set_s3_target_folder(self):
        """
        Test setting the s3 target folder
        """
        self.set_up(setup_s3_uploading=True)
        self.assertEqual("testing", self.ocw_parser.s3_target_folder)
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