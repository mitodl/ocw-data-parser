import os
import shutil
import json
import boto3

"""
This is a class used for downloading source json from S3 based on a list of course id's

An example of the expected format can be found in example_courses.json
"""


class OCWDownloader(object):
    def __init__(self,
                 courses_json="",
                 env="QA",
                 destination_dir="",
                 s3_bucket_name="",
                 overwrite=False):
        self.courses_json = courses_json
        self.env = env
        self.destination_dir = destination_dir
        self.s3_bucket_name = s3_bucket_name
        self.overwrite = overwrite

    def download_courses(self):
        courses = None
        with open(self.courses_json) as f:
            courses = json.load(f)["courses"]
        if not os.path.exists(self.destination_dir):
            os.makedirs(self.destination_dir)
        s3_client = boto3.client("s3")

        paginator = s3_client.get_paginator("list_objects")
        pages = paginator.paginate(Bucket=self.s3_bucket_name)
        for page in pages:
            for obj in page["Contents"]:
                key_parts = obj["Key"].split("/")
                if len(key_parts) > 3:
                    course_id = key_parts[-3]
                    if course_id in courses:
                        # make the destination path if it doesn't exist and download all files
                        raw_course_path = os.path.join(
                            self.destination_dir, course_id, "0")
                        if not os.path.exists(raw_course_path):
                            os.makedirs(raw_course_path)
                        dest_filename = os.path.join(
                            raw_course_path, os.path.basename(os.path.normpath(obj["Key"])))
                        if (os.path.exists(dest_filename) and self.overwrite):
                            os.remove(dest_filename)
                        if not os.path.exists(dest_filename):
                            print("downloading {}...".format(
                                dest_filename))
                            with open(dest_filename, "wb+") as f:
                                s3_client.download_fileobj(
                                    self.s3_bucket_name, obj["Key"], f)
                        courses.pop(courses.index(course_id))
        
        # if there are still courses in the list, that means they weren't found on s3
        if len(courses) > 0:
            print("The following courses were not found in the s3 bucket {}:".format(self.s3_bucket_name))
            for course_id in courses:
                print(" - {}".format(course_id))