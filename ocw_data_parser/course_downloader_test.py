import os
import shutil
import pytest
from mock import patch
import filecmp
from tempfile import TemporaryDirectory
import logging
log = logging.getLogger(__name__)
import ocw_data_parser.test_constants as constants

"""
Tests for course_downlader
"""


def test_download_courses(ocw_downloader):
    """
    Use moto (mock boto) to test s3 downloading and make sure all files 
    end up where they're supposed to
    """
    ocw_downloader.download_courses()
    for root, dirs, files in os.walk(constants.COURSE_DIR):
        if len(dirs) == 0 and len(files) > 0:
            path, folder = os.path.split(root)
            if folder == "jsons":
                path, course = os.path.split(path)
                for json_file in files:
                    test_data_path = os.path.join(path, course, "jsons", json_file)
                    downloaded_path = os.path.join(ocw_downloader.destination_dir, constants.S3_TEST_COURSE_ROOT, course, "0", json_file)
                    assert filecmp.cmp(test_data_path, downloaded_path)


def test_download_courses_no_destination_dir(ocw_downloader):
    """
    Download the courses, but delete the destination dir first, then ensure 
    the process runs without error and the directory is recreated
    """
    with patch.object(os, "makedirs", wraps=os.makedirs) as mock:
        shutil.rmtree(ocw_downloader.destination_dir)
        ocw_downloader.download_courses()
        mock.assert_any_call(ocw_downloader.destination_dir)


@pytest.mark.parametrize("prefix,downloaded", [["PROD", True], ["QA", False]])
def test_download_courses_skip_nonmatching_prefix(ocw_downloader, prefix, downloaded):
    """
    Courses that don't match the specified prefix should not be downloaded
    """
    ocw_downloader.prefix = prefix
    ocw_downloader.download_courses()
    downloaded_path = os.path.join(ocw_downloader.destination_dir, constants.S3_TEST_COURSE_ROOT)
    assert os.path.exists(downloaded_path) is downloaded


def test_download_courses_missing_course(ocw_downloader, capfd):
    """
    Download the courses, but add a course to courses.json that doesn't exist first
    """
    ocw_downloader.courses_json = "ocw_data_parser/test_json/courses_missing.json"
    ocw_downloader.download_courses()
    out, err = capfd.readouterr()
    assert "missing was not found in the s3 bucket testing" in out


def test_download_courses_overwrite(ocw_downloader):
    """
    Download the courses, then mark overwrite as true and do it again and 
    ensure that os.remove is called for each file
    """
    with patch.object(os, "remove", wraps=os.remove) as mock:
        ocw_downloader.download_courses()
        ocw_downloader.overwrite = True
        ocw_downloader.download_courses()
        for root, dirs, files in os.walk(ocw_downloader.destination_dir):
            if len(dirs) == 0 and len(files) > 0:
                path, folder = os.path.split(root)
                if folder == "0":
                    path, course = os.path.split(path)
                    for json_file in files:
                        downloaded_path = os.path.join(path, course, "0", json_file)
                        mock.assert_any_call(downloaded_path)
