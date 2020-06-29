import os
import pytest
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
    Use moto (mock boto) to test s3 downloading
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
