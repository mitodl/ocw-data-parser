import os
from pathlib import Path
import json
import boto3

"""
This is a class used for downloading source json from S3 based on a list of course id's

An example of the expected format can be found in example_courses.json
"""


class OCWDownloader:
    def __init__(self,
                 courses_json=None,
                 prefix="PROD",
                 destination_dir=None,
                 s3_bucket_name="",
                 overwrite=False,
        ):
        self.courses_json = Path(courses_json) if courses_json else None
        self.destination_dir = Path(destination_dir) if destination_dir else None
        self.s3_bucket_name = s3_bucket_name
        self.overwrite = overwrite
        self.prefix = prefix

    def download_courses(self):
        downloaded_courses = []
        with open(self.courses_json) as f:
            courses = json.load(f)["courses"]
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
                        raw_course_path = Path(
                            self.destination_dir, *key_parts[0:-1])
                        os.makedirs(raw_course_path, exist_ok=True)
                        key_basename = os.path.basename(os.path.normpath(obj["Key"]))
                        dest_filename = raw_course_path / key_basename
                        if dest_filename.exists() and self.overwrite:
                            os.remove(dest_filename)
                        if not dest_filename.exists():
                            print("downloading {}...".format(
                                dest_filename))
                            with open(dest_filename, "wb+") as f:
                                s3_client.download_fileobj(
                                    self.s3_bucket_name, obj["Key"], f)
                                if course_id not in downloaded_courses:
                                    downloaded_courses.append(course_id)
        
        # make sure everything downloaded right
        for course_id in courses:
            if course_id not in downloaded_courses:
                print("{} was not found in the s3 bucket {}".format(course_id, self.s3_bucket_name))