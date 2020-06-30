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
        self.destinationDir = destination_dir
        self.s3BucketName = s3_bucket_name
        self.overwrite = overwrite

    def downloadCourses(self):
        courses = None
        with open(self.coursesJson) as f:
            courses = json.load(f)["courses"]
        if not os.path.exists(self.destinationDir):
            os.makedirs(self.destinationDir)
        s3 = boto3.resource("s3")
        s3Client = boto3.client("s3")
        ocwContentStorage = s3.Bucket(self.s3BucketName)
        allObjects = ocwContentStorage.meta.client.list_objects(
            Bucket=ocwContentStorage.name, Prefix="{}/".format(self.env), Delimiter="/")

        # first tier subfolders under env should be department numbers
        for departmentPath in allObjects.get("CommonPrefixes"):
            # second tier subfolders should be course numbers
            courseNumbers = ocwContentStorage.meta.client.list_objects(
                Bucket=ocwContentStorage.name, Prefix=departmentPath.get("Prefix"), Delimiter="/")
            for courseNumberPath in courseNumbers.get("CommonPrefixes"):
                # third tier folders should be course terms
                courseTerms = ocwContentStorage.meta.client.list_objects(
                    Bucket=ocwContentStorage.name, Prefix=courseNumberPath.get("Prefix"), Delimiter="/")
                for courseTerm in courseTerms.get("CommonPrefixes"):
                    # fourth tier folders should be course folders keyed with the course id
                    courseFolders = ocwContentStorage.meta.client.list_objects(
                        Bucket=ocwContentStorage.name, Prefix=courseTerm.get("Prefix"), Delimiter="/")
                    for courseFolder in courseFolders.get("CommonPrefixes"):
                        # make sure the course is in our list
                        courseId = os.path.basename(
                            os.path.normpath(courseFolder.get("Prefix")))
                        if courseId in courses:
                            # make the destination path if it doesn't exist and download all files
                            rawCoursePath = os.path.join(
                                self.destinationDir, courseId, "0")
                            if not os.path.exists(rawCoursePath):
                                os.makedirs(rawCoursePath)
                            for courseFile in ocwContentStorage.objects.filter(Prefix=os.path.join(courseFolder.get("Prefix", "0"))):
                                destFilename = os.path.join(
                                    rawCoursePath, os.path.basename(os.path.normpath(courseFile.key)))
                                if (os.path.exists(destFilename) and self.overwrite):
                                    os.remove(destFilename)
                                if not os.path.exists(destFilename):
                                    print("downloading {}...".format(
                                        destFilename))
                                    with open(destFilename, "wb+") as f:
                                        s3Client.download_fileobj(
                                            ocwContentStorage.name, courseFile.key, f)
