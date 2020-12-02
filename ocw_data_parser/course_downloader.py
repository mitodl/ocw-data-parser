"""
This is a class used for downloading source json from S3 based on a list of course id's

An example of the expected format can be found in example_courses.json
"""

import json
import os
from pathlib import Path

import boto3


class OCWDownloader:  # pylint: disable=too-few-public-methods
    """Downloads input JSON from an S3 bucket"""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        courses_json=None,
        prefix="PROD",
        destination_dir=None,
        s3_bucket_name="",
        overwrite=False,
    ):
        """

        Args:
            courses_json (str or Path or None): Path to the JSON file with the list of courses
            prefix (str): The prefix to use when filtering courses in the bucket
            destination_dir (str or Path or None):
                Path to the destination directory. If it doesn't exist it will be created.
            s3_bucket_name (str): S3 bucket to download courses from
            overwrite (bool): If true, file will be replaced if it already exists
        """
        self.courses_json = Path(courses_json) if courses_json else None
        self.destination_dir = Path(destination_dir) if destination_dir else None
        self.s3_bucket_name = s3_bucket_name
        self.overwrite = overwrite
        self.prefix = prefix

    def download_courses(self):
        """
        Download each matching course
        """
        downloaded_courses = []
        with open(self.courses_json) as file:
            courses = json.load(file)["courses"]
        os.makedirs(self.destination_dir, exist_ok=True)
        s3_client = boto3.client("s3")

        paginator = s3_client.get_paginator("list_objects")
        pages = paginator.paginate(Bucket=self.s3_bucket_name)
        for page in pages:
            for obj in page["Contents"]:
                key_parts = obj["Key"].split("/")
                if len(key_parts) > 3 and key_parts[0] == self.prefix:
                    course_id = key_parts[-3]
                    if course_id in courses:
                        # make the destination path if it doesn't exist and download all files
                        raw_course_path = Path(self.destination_dir, *key_parts[0:-1])
                        os.makedirs(raw_course_path, exist_ok=True)
                        key_basename = os.path.basename(os.path.normpath(obj["Key"]))
                        dest_filename = raw_course_path / key_basename
                        if dest_filename.exists() and self.overwrite:
                            os.remove(dest_filename)
                        if not dest_filename.exists():
                            print("downloading {}...".format(dest_filename))
                            with open(dest_filename, "wb+") as file:
                                s3_client.download_fileobj(
                                    self.s3_bucket_name, obj["Key"], file
                                )
                                if course_id not in downloaded_courses:
                                    downloaded_courses.append(course_id)

        # make sure everything downloaded right
        for course_id in courses:
            if course_id not in downloaded_courses:
                print(
                    "{} was not found in the s3 bucket {}".format(
                        course_id, self.s3_bucket_name
                    )
                )
