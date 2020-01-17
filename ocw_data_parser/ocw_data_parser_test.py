"""
Tests for ocw_data_parser
"""
import json
import pytest
import os
import shutil
import responses
import boto3
from moto import mock_s3
from ocw_data_parser.ocw_data_parser import CustomHTMLParser, OCWParser
from ocw_data_parser.utils import update_file_location, get_binary_data, is_json, get_correct_path, load_json_file, print_error, print_success, safe_get, find_all_values_for_key

"""
Tests for OCW Parser
"""

@pytest.fixture(autouse=True, scope="session")
def s3_bucket():
    with mock_s3():
        conn = boto3.client('s3',
                            aws_access_key_id="testing",
                            aws_secret_access_key="testing")
        conn.create_bucket(Bucket="testing")
        responses.add_passthru("https://")
        responses.add_passthru("http://")
        s3 = boto3.resource('s3',
                            aws_access_key_id="testing",
                            aws_secret_access_key="testing")
        s3_bucket = s3.Bucket(name="testing")
        yield s3_bucket

@pytest.fixture(autouse=True, scope="function")
def ocw_parser():
    """
    Instantiate an OCWParser object and run functions depending on args passed in
    """
    yield OCWParser(course_dir="ocw_data_parser/test_json/course_dir",
                        destination_dir="ocw_data_parser/test_json/destination_dir",
                        static_prefix="static_files/")
    destination_dir = "ocw_data_parser/test_json/destination_dir"
    if os.path.isdir(destination_dir):
        shutil.rmtree(destination_dir)

@pytest.fixture(autouse=True, scope="session")
def ocw_parser_s3():
    parser = OCWParser(course_dir="ocw_data_parser/test_json/course_dir",
                        destination_dir="ocw_data_parser/test_json/destination_dir",
                        static_prefix="static_files/")
    parser.setup_s3_uploading(
        s3_bucket_name="testing",
        s3_bucket_access_key="testing",
        s3_bucket_secret_access_key="testing",
        folder="testing"
    )
    
    yield parser

@pytest.fixture(autouse=True)
def course_id(ocw_parser):
    yield ocw_parser.master_json["short_url"]

# utils.py

def test_update_local_file_location(ocw_parser):
    """
    Extract local course media, update the location of one of the files 
    and then assert that the location has indeed changed
    """
    ocw_parser.extract_media_locally()
    if len(ocw_parser.master_json["course_files"]) > 0:
        test_file = ocw_parser.master_json["course_files"][0]
        original_location = test_file["file_location"]
        update_file_location(ocw_parser.master_json,
                                'test_location', obj_uid=test_file["uid"])
        assert original_location != ocw_parser.master_json["course_files"][0]["file_location"]
    else:
        fail("test course has no local media to test")

def test_update_foreign_file_location(ocw_parser):
    """
    Extract foreign course media, update the location of one of the files 
    and then assert that the location has indeed changed
    """
    ocw_parser.extract_foreign_media_locally()
    if len(ocw_parser.master_json["course_foreign_files"]) > 0:
        test_file = ocw_parser.master_json["course_foreign_files"][0]
        original_location = test_file["file_location"]
        original_filename = test_file["link"].split("/")[-1]
        update_file_location(ocw_parser.master_json,
                                'test_location/' + original_filename)
        assert original_location != ocw_parser.master_json["course_foreign_files"][0]["file_location"]
    else:
        fail("test course has no foreign media to test")

def test_get_binary_data_none(ocw_parser):
    """
    Find the first file without a datafield property and attempt to get the binary data from it
    """
    if len(ocw_parser.master_json["course_files"]) > 0:
        for media in ocw_parser.master_json["course_files"]:
            if "_datafield_image" not in media and "_datafield_file" not in media:
                data = get_binary_data(media)
                assert data is None
    else:
        fail("test course has no local media to test")

def test_get_correct_path_none(ocw_parser):
    """
    Test passing in invalid data to get_correct_path
    """
    get_correct_path(None)

def test_load_invalid_json_file(ocw_parser):
    """
    Test passing in an invalid JSON file (this one)
    """
    assert load_json_file('ocw_data_parser/ocw_data_parser_test.py') is None

def test_print_error(ocw_parser):
    """
    Test printing an error doesn't throw an exception
    """
    try:
        print_error("Error!")
    except:
        fail("print_error raised an exception")

def test_print_success(ocw_parser):
    """
    Test that printing a success message doesn't throw an exception
    """
    try:
        print_success("Success!")
    except:
        fail("print_success raised an exception")

def test_safe_get_invalid_value(ocw_parser):
    """
    Test trying to get a value from a dict that doesn't exist
    """
    test_dict = {
        "value_one": "1",
        "value_two": "2",
        "actual_file_name": 'test'
    }
    assert safe_get(test_dict, "value_three", print_error_message=True) is None

# ocw_data_parser.py

def test_no_params(ocw_parser):
    """
    Test that an OCWParser with no params raises an exception
    """
    with pytest.raises(Exception):
        OCWParser()

def test_html_parser_output_list(ocw_parser):
    """
    Test passing in an output_list to the CustomHTMLParser
    """
    output_list = ['test']
    parser = CustomHTMLParser(output_list=output_list)
    assert 'test' == parser.output_list[0]

def test_parser_loaded_jsons(ocw_parser):
    """
    Test instantiating a parser with preloaded jsons
    """
    try:
        assert OCWParser(loaded_jsons=ocw_parser.jsons)
    except:
        fail("instantiating parser with preloaded jsons failed")

def test_generate_master_json_none_source(ocw_parser):
    """
    Make sure that running generate_master_json doesn't throw an error after nulling 
    out the parser's source jsons
    """
    ocw_parser.jsons = None
    ocw_parser.generate_master_json()
    assert ocw_parser.jsons is not None

def test_generate_master_json_none_course_image_uid(ocw_parser):
    """
    Make sure course_image_uid is regenerated by generate_master_json after it's nulled out
    """
    ocw_parser.course_image_uid = None
    ocw_parser.generate_master_json()
    assert ocw_parser.course_image_uid is not None

def test_load_raw_jsons_invalid_file(ocw_parser):
    """
    Add a json file with invalid content to the course_dir and make sure it generates an error
    """
    with open("ocw_data_parser/test_json/course_dir/jsons/999.json", "w") as f:
        f.write("{")
    try:
        OCWParser(course_dir="ocw_data_parser/test_json/course_dir",
                destination_dir="ocw_data_parser/test_json/destination_dir",
                static_prefix="static_files/")
        assert False
    except:
        assert True
    os.remove("ocw_data_parser/test_json/course_dir/jsons/999.json")

def test_upload_all_data_to_s3(ocw_parser_s3, s3_bucket):
    """
    Use moto (mock boto) to test s3 uploading
    """
    ocw_parser_s3.upload_all_media_to_s3(upload_master_json=True)
    course_image_key = None
    for bucket_item in s3_bucket.objects.filter(Prefix=ocw_parser_s3.s3_target_folder):
        if bucket_item.key in ocw_parser_s3.course_image_s3_link:
            course_image_key = bucket_item.key
    assert course_image_key is not None

def test_upload_course_image(ocw_parser_s3, s3_bucket):
    """
    Use moto (mock boto) to test s3 uploading
    """
    ocw_parser_s3.upload_course_image()
    course_image_key = None
    for bucket_item in s3_bucket.objects.filter(Prefix=ocw_parser_s3.s3_target_folder):
        if bucket_item.key in ocw_parser_s3.course_image_s3_link:
            course_image_key = bucket_item.key
    assert course_image_key is not None

def test_get_master_json(ocw_parser):
    """
    Test that getting the master JSON is not None or empty and doesn't throw an exception
    """
    try:
        assert ocw_parser.get_master_json()
    except:
        fail("get_master_json raised an exception")

def test_set_s3_bucket_name(ocw_parser_s3):
    """
    Test setting the s3 bucket name
    """
    assert "testing" == ocw_parser_s3.s3_bucket_name

def test_set_s3_access_key(ocw_parser_s3):
    """
    Test setting the s3 access key
    """
    assert "testing" == ocw_parser_s3.s3_bucket_access_key

def test_set_s3_secret_access_key(ocw_parser_s3):
    """
    Test setting the s3 secret access key
    """
    assert "testing" == ocw_parser_s3.s3_bucket_secret_access_key

def test_set_s3_target_folder(ocw_parser_s3):
    """
    Test setting the s3 target folder
    """
    assert "testing/" == ocw_parser_s3.s3_target_folder

def test_uid(ocw_parser, course_id):
    """
    Test that the uid property of the master JSON matches the uid of the course site root
    """
    ocw_parser.generate_static_site()
    with open('ocw_data_parser/test_json/course_dir/jsons/1.json', 'r') as first_json:
        first_json_data = json.loads(first_json.read())
        with open('ocw_data_parser/test_json/destination_dir/{}/master/master.json'.format(course_id), 'r') as master_json:
            master_json_data = json.loads(master_json.read())
            assert first_json_data["_uid"] == master_json_data["uid"]
