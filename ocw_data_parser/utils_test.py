"""Tests for utility functions"""
from base64 import b64encode
import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

import ocw_data_parser.test_constants as constants
from ocw_data_parser.utils import (
    update_file_location,
    get_binary_data,
    print_error,
    print_success,
    htmlify,
    parse_all,
    is_course_published,
)


# pylint: disable=unused-argument
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


@pytest.mark.parametrize("base64_key", ["_datafield_image", "_datafield_file", None])
@pytest.mark.parametrize("url_key", ["unique_identifier", "technical_location", None])
@pytest.mark.parametrize("is_valid_request", [True, False])
def test_get_binary_data(mocker, ocw_parser, base64_key, url_key, is_valid_request):
    """
    get_binary_data should look up base64 encoded values from certain addresses
    """
    data = b"abcde"
    url = "http://example.mit.edu/a/url"
    get_mock = mocker.patch("requests.get")
    get_mock.return_value.ok = is_valid_request
    get_mock.return_value.content = data

    media = {}
    if base64_key is not None:
        media[base64_key] = {"data": b64encode(data)}
    if url_key is not None:
        media[url_key] = url

    out_data = get_binary_data(media)
    if base64_key is not None:
        # data should be successfully fetched from base64 data
        expected = data
    elif url_key is not None and is_valid_request:
        # data should be successfully fetched from the internet
        expected = data
    else:
        expected = None

    assert expected == out_data

    if url_key is not None and base64_key is None:
        get_mock.assert_called_once_with(url)


def test_get_binary_data_url(ocw_parser):
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
    invalid_path = "/fake_path"
    with pytest.raises(Exception) as ex:
        is_course_published(invalid_path)
    assert ex.value.args[0] == (f"Could not find 1.json for {invalid_path}")
