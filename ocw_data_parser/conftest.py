import os
import shutil
import pytest
import responses
import boto3
from moto import mock_s3
import ocw_data_parser.test_constants as constants
from ocw_data_parser.ocw_data_parser import OCWParser
from ocw_data_parser.course_downloader import OCWDownloader
from tempfile import TemporaryDirectory

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
def s3_bucket_populated(s3_bucket):
    if (os.path.isdir(constants.COURSE_DIR)):
        for course in os.listdir(constants.COURSE_DIR):
            course_dir = os.path.join(constants.COURSE_DIR, course, "jsons")
            if os.path.isdir(course_dir):
                for filename in os.listdir(course_dir):
                    s3_bucket.upload_file(os.path.join(course_dir, filename), os.path.join(constants.S3_TEST_COURSE_ROOT, course, "0", filename))
    yield s3_bucket

@pytest.fixture(autouse=True, scope="function")
def ocw_parser():
    """
    Instantiate an OCWParser object and run functions depending on args passed in
    """
    with TemporaryDirectory() as destination_dir:
        yield OCWParser(course_dir="ocw_data_parser/test_json/course_dir/course-1",
                            destination_dir=destination_dir,
                            static_prefix="static_files/")

@pytest.fixture(autouse=True, scope="function")
def ocw_parser_s3(ocw_parser):
    ocw_parser.setup_s3_uploading(
        s3_bucket_name="testing",
        s3_bucket_access_key="testing",
        s3_bucket_secret_access_key="testing",
        folder="course-1"
    )
    yield ocw_parser

@pytest.fixture(autouse=True)
def course_id(ocw_parser):
    yield ocw_parser.parsed_json["short_url"]

@pytest.fixture(autouse=True)
def ocw_downloader(s3_bucket_populated):
    with TemporaryDirectory() as destination_dir:
        yield OCWDownloader("ocw_data_parser/test_json/courses.json", destination_dir=destination_dir, s3_bucket_name="testing")
