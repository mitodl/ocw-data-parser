import os
import pytest
from ocw_data_parser.ocw_data_parser_test import ocw_parser
from ocw_data_parser.utils import update_file_location, get_binary_data, is_json, get_correct_path, load_json_file, print_error, print_success, safe_get, find_all_values_for_key


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
                             "test_location", obj_uid=test_file["uid"])
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
                             os.path.join("test_location/", original_filename))
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
    assert load_json_file("ocw_data_parser/ocw_data_parser_test.py") is None


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
        "actual_file_name": "test"
    }
    assert safe_get(test_dict, "value_three", print_error_message=True) is None
