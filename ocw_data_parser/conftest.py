import os
import shutil
import pytest
import responses
import boto3
from moto import mock_s3
from ocw_data_parser.ocw_data_parser import OCWParser

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