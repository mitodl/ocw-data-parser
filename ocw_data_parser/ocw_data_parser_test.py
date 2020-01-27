import os
import json
import pytest
from tempfile import TemporaryDirectory
from ocw_data_parser.ocw_data_parser import CustomHTMLParser, OCWParser
import ocw_data_parser.test_constants as constants
import logging
log = logging.getLogger(__name__)

"""
Tests for ocw_data_parser
"""

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
    output_list = ["test"]
    parser = CustomHTMLParser(output_list=output_list)
    assert "test" == parser.output_list[0]

def test_parser_loaded_jsons(ocw_parser):
    """
    Test instantiating a parser with preloaded jsons
    """
    assert OCWParser(loaded_jsons=ocw_parser.jsons), "instantiating parser with preloaded jsons failed"

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
    with TemporaryDirectory() as destination_dir:
        with open(os.path.join(constants.COURSE_DIR, "jsons/999.json"), "w") as f:
            f.write("{")
        with pytest.raises(json.decoder.JSONDecodeError):
            OCWParser(course_dir=constants.COURSE_DIR,
                        destination_dir=destination_dir,
                        static_prefix=constants.STATIC_PREFIX)
        os.remove(os.path.join(constants.COURSE_DIR, "jsons/999.json"))

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
    Test that getting the master JSON is not None or empty or missing basic properties 
    and doesn't throw an exception
    """
    fail_template = "failed to read {} property from master json"
    master_json = ocw_parser.get_master_json()
    assert master_json, "failed to get master json"
    assert master_json["uid"], fail_template.format("uid")
    assert master_json["title"], fail_template.format("title")
    assert master_json["description"], fail_template.format("description")
    assert master_json["short_url"], fail_template.format("short_url")

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
    assert "testing" == ocw_parser_s3.s3_target_folder

def test_uid(ocw_parser, course_id):
    """
    Test that the uid property of the master JSON matches the uid of the course site root
    """
    ocw_parser.generate_static_site()
    with open(os.path.join(constants.COURSE_DIR, "jsons/1.json"), "r") as first_json:
        first_json_data = json.loads(first_json.read())
        with open(os.path.join(ocw_parser.destination_dir, "master/master.json"), "r") as master_json:
            master_json_data = json.loads(master_json.read())
            assert first_json_data["_uid"] == master_json_data["uid"]
