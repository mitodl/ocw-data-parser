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
        self.coursesJson = courses_json
        self.env = env
        self.destination_dir = destination_dir
        self.s3_bucket_name = s3_bucket_name
        self.overwrite = overwrite

    def download_courses(self):
        courses = None
        with open(self.coursesJson) as f:
            courses = json.load(f)["courses"]
        if not os.path.exists(self.destination_dir):
            os.makedirs(self.destination_dir)
        s3 = boto3.resource("s3")
        s3_client = boto3.client("s3")
        ocw_content_storage = s3.Bucket(self.s3_bucket_name)
        all_objects = ocw_content_storage.meta.client.list_objects(
            Bucket=ocw_content_storage.name, Prefix="{}/".format(self.env), Delimiter="/")

        # first tier subfolders under env should be department numbers
        for department_path in all_objects.get("CommonPrefixes"):
            # second tier subfolders should be course numbers
            course_numbers = ocw_content_storage.meta.client.list_objects(
                Bucket=ocw_content_storage.name, Prefix=department_path.get("Prefix"), Delimiter="/")
            for course_number_path in course_numbers.get("CommonPrefixes"):
                # third tier folders should be course terms
                course_terms = ocw_content_storage.meta.client.list_objects(
                    Bucket=ocw_content_storage.name, Prefix=course_number_path.get("Prefix"), Delimiter="/")
                for course_term in course_terms.get("CommonPrefixes"):
                    # fourth tier folders should be course folders keyed with the course id
                    course_folders = ocw_content_storage.meta.client.list_objects(
                        Bucket=ocw_content_storage.name, Prefix=course_term.get("Prefix"), Delimiter="/")
                    for course_folder in course_folders.get("CommonPrefixes"):
                        # make sure the course is in our list
                        course_id = os.path.basename(
                            os.path.normpath(course_folder.get("Prefix")))
                        if course_id in courses:
                            # make the destination path if it doesn't exist and download all files
                            raw_course_path = os.path.join(
                                self.destination_dir, course_id, "0")
                            if not os.path.exists(raw_course_path):
                                os.makedirs(raw_course_path)
                            for course_file in ocw_content_storage.objects.filter(Prefix=os.path.join(course_folder.get("Prefix", "0"))):
                                dest_filename = os.path.join(
                                    raw_course_path, os.path.basename(os.path.normpath(course_file.key)))
                                if (os.path.exists(dest_filename) and self.overwrite):
                                    os.remove(dest_filename)
                                if not os.path.exists(dest_filename):
                                    print("downloading {}...".format(
                                        dest_filename))
                                    with open(dest_filename, "wb+") as f:
                                        s3_client.download_fileobj(
                                            ocw_content_storage.name, course_file.key, f)
