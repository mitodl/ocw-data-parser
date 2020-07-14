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
    for root, dirs, files in os.walk(ocw_downloader.destination_dir):
        if len(dirs) == 0 and len(files) > 0:
            path, folder = os.path.split(root)
            if folder == "0":
                path, course = os.path.split(path)
                for json_file in files:
                    test_data_path = os.path.join(constants.COURSE_DIR, course, "jsons", json_file)
                    downloaded_path = os.path.join(path, course, "0", json_file)
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