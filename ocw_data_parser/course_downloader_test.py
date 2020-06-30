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
    ocw_downloader.downloadCourses()
    for root, dirs, files in os.walk(ocw_downloader.destinationDir):
        if len(dirs) == 0 and len(files) > 0:
            path, folder = os.path.split(root)
            if folder == "0":
                path, course = os.path.split(path)
                for jsonFile in files:
                    testDataPath = os.path.join(constants.COURSE_DIR, course, "jsons", jsonFile)
                    downloadedPath = os.path.join(path, course, "0", jsonFile)
                    assert filecmp.cmp(testDataPath, downloadedPath)

def test_download_courses_no_destination_dir(ocw_downloader):
    """
    Download the courses, but delete the destination dir first, then ensure 
    the process runs without error and the directory is recreated
    """
    with patch.object(os, "makedirs", wraps=os.makedirs) as mock:
        shutil.rmtree(ocw_downloader.destinationDir)
        ocw_downloader.downloadCourses()
        mock.assert_any_call(ocw_downloader.destinationDir)

def test_download_courses_overwrite(ocw_downloader):
    """
    Download the courses, then mark overwrite as true and do it again and 
    ensure that os.remove is called for each file
    """
    with patch.object(os, "remove", wraps=os.remove) as mock:
        ocw_downloader.downloadCourses()
        ocw_downloader.overwrite = True
        ocw_downloader.downloadCourses()
        for root, dirs, files in os.walk(ocw_downloader.destinationDir):
            if len(dirs) == 0 and len(files) > 0:
                path, folder = os.path.split(root)
                if folder == "0":
                    path, course = os.path.split(path)
                    for jsonFile in files:
                        downloadedPath = os.path.join(path, course, "0", jsonFile)
                        mock.assert_any_call(downloadedPath)
