import os
import json
import pytest
from tempfile import TemporaryDirectory

from mock import patch

import ocw_data_parser.test_constants as constants
from ocw_data_parser.utils import (
    update_file_location,
    get_binary_data,
    get_correct_path,
    load_json_file,
    print_error,
    print_success,
    htmlify,
    parse_all,
    is_course_published,
)


def test_update_local_file_location(ocw_parser):
    """
    Extract local course media, update the location of one of the files
    and then assert that the location has indeed changed
    """
    ocw_parser.extract_media_locally()
    assert (
        len(ocw_parser.parsed_json["course_files"]) > 0
    ), "test course has no local media to test"
    test_file = ocw_parser.parsed_json["course_files"][0]
    original_location = test_file["file_location"]
    update_file_location(
        ocw_parser.parsed_json, "test_location", obj_uid=test_file["uid"]
    )
    assert (
        original_location != ocw_parser.parsed_json["course_files"][0]["file_location"]
    ), "failed to update local file location"


def test_update_foreign_file_location(ocw_parser):
    """
    Extract foreign course media, update the location of one of the files
    and then assert that the location has indeed changed
    """
    ocw_parser.extract_foreign_media_locally()
    assert (
        len(ocw_parser.parsed_json["course_foreign_files"]) > 0
    ), "test course has no foreign media to test"
    test_file = ocw_parser.parsed_json["course_foreign_files"][0]
    original_location = test_file["file_location"]
    original_filename = test_file["link"].split("/")[-1]
    update_file_location(
        ocw_parser.parsed_json, os.path.join("test_location/", original_filename)
    )
    assert (
        original_location
        != ocw_parser.parsed_json["course_foreign_files"][0]["file_location"]
    ), "failed to update foreign file location"


def test_get_binary_data_none(ocw_parser):
    """
    Find the first file without a datafield property and attempt to get the binary data from it
    """
    assert (
        len(ocw_parser.parsed_json["course_files"]) > 0
    ), "test course has no local media to test"
    found = False
    for media in ocw_parser.parsed_json["course_files"]:
        if "_datafield_image" not in media and "_datafield_file" not in media:
            found = True
            data = get_binary_data(media)
            assert (
                data is None
            ), "unexpected binary data in non _datafield_image or _datafield_file media"
    assert found, "test course has no file without a datafield property"


def test_get_correct_path_none(ocw_parser):
    """
    Test passing in invalid data to get_correct_path
    """
    assert get_correct_path(None) == ""


def test_load_invalid_json_file(ocw_parser):
    """
    Test passing in an invalid JSON file (this one)
    """
    with pytest.raises(json.decoder.JSONDecodeError):
        load_json_file("ocw_data_parser/ocw_data_parser_test.py")


def test_print_error(ocw_parser):
    """
    Test printing an error doesn't throw an exception
    """
    print_error("Error!")


def test_print_success(ocw_parser):
    """
    Test that printing a success message doesn't throw an exception
    """
    print_success("Success!")


def test_htmlify(ocw_parser):
    """
    Test that calling htmlify on a page returns some html and a filename
    """
    parsed_json = ocw_parser.get_parsed_json()
    course_pages = parsed_json.get("course_pages")
    test_page = course_pages[0]
    filename, html = htmlify(test_page)
    assert filename == test_page["uid"] + "_" + test_page["short_url"] + ".html"
    assert "<html>" in html
    assert "</html>" in html
    assert "<body>" in html
    assert "</body>" in html
    assert test_page["text"] in html


def test_parse_all():
    """
    Test that all expected parsed json files are written to the output directory
    """
    with TemporaryDirectory() as destination_dir:
        parse_all(constants.COURSE_DIR, destination_dir)
        assert os.path.isdir(os.path.join(destination_dir, "course-1"))
        assert os.path.isdir(os.path.join(destination_dir, "course-2"))


@pytest.mark.parametrize("upload_parsed_json", [True, False])
@pytest.mark.parametrize("s3_links", [True, False])
@pytest.mark.parametrize("is_published", [True, False])
def test_parse_all(upload_parsed_json, s3_links, is_published):
    """
    Test that OCWParser.export_parsed_json is called with the expected arguments
    """
    with patch("ocw_data_parser.utils.is_course_published", return_value=is_published):
        with patch("ocw_data_parser.OCWParser") as mock_parser:
            with TemporaryDirectory() as destination_dir:
                parse_all(
                    constants.COURSE_DIR,
                    destination_dir,
                    s3_links=s3_links,
                    upload_parsed_json=upload_parsed_json,
                )
                assert mock_parser.return_value.export_parsed_json.call_count == 2
                mock_parser.return_value.export_parsed_json.assert_any_call(
                    s3_links=s3_links,
                    upload_parsed_json=(
                        s3_links and is_published and upload_parsed_json
                    ),
                )


@pytest.mark.parametrize(
    "last_published,last_unpublished,is_published",
    [
        [None, None, False],
        ["2016/02/02 20:28:06 US/Eastern", None, True],
        ["2016/02/02 20:28:06 US/Eastern", "2015/02/02 20:28:06 US/Eastern", True],
        ["2016/02/02 20:28:06 US/Eastern", "2018/02/02 20:28:06 US/Eastern", False],
    ],
)
def test_is_course_published(last_published, last_unpublished, is_published):
    """
    Test that the expected value is returned from is_course_published
    """
    sample_json = {
        "last_published_to_production": last_published,
        "last_unpublishing_date": last_unpublished,
    }
    with patch("os.path.exists", return_value=True), patch(
        "json.load", return_value=sample_json
    ):
        assert (
            is_course_published(
                "{}/".format(os.path.join(constants.COURSE_DIR, "course-1"))
            )
            == is_published
        )


def test_is_course_published_not_found():
    """
    Test that an error is logged if 1.json can't be found
    """
    with patch("ocw_data_parser.utils.log.error") as mock_log:
        is_course_published("/fake_path")
        mock_log.assert_called_once_with(
            "Could not find 1.json for %s", "/fake_path", exc_info=True
        )


def test_is_course_published_bad_data():
    """
    Test that an error is logged if 1.json can't be parsed for dates
    """
    sample_json = {
        "last_published_to_production": "a b",
        "last_unpublishing_date": "TBA",
    }
    with patch("ocw_data_parser.utils.log.error") as mock_log, patch(
        "os.path.exists", return_value=True
    ), patch("ocw_data_parser.utils.glob", return_value=["1.json"]), patch(
        "json.load", return_value=sample_json
    ):
        is_course_published(
            "{}/".format(os.path.join(constants.COURSE_DIR, "course-1"))
        )
        mock_log.assert_called_once_with(
            "Error encountered reading 1.json for %s",
            "ocw_data_parser/test_json/course_dir/course-1/",
            exc_info=True,
        )
