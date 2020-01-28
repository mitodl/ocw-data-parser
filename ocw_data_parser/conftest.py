import os
import shutil
import pytest
import responses
import boto3
from moto import mock_s3
from ocw_data_parser.ocw_data_parser import OCWParser
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
def ocw_parser():
    """
    Instantiate an OCWParser object and run functions depending on args passed in
    """
    with TemporaryDirectory() as destination_dir:
        yield OCWParser(course_dir="ocw_data_parser/test_json/course_dir",
                            destination_dir=destination_dir,
                            static_prefix="static_files/")

@pytest.fixture(autouse=True, scope="function")
def ocw_parser_s3(ocw_parser):
    ocw_parser.setup_s3_uploading(
        s3_bucket_name="testing",
        s3_bucket_access_key="testing",
        s3_bucket_secret_access_key="testing",
        folder="testing"
    )
    
    yield ocw_parser

@pytest.fixture(autouse=True)
def course_id(ocw_parser):
    yield ocw_parser.master_json["short_url"]