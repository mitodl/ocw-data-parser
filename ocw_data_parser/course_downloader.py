import os
import shutil
import json
import boto3


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

        for departmentPath in allObjects.get("CommonPrefixes"):
            courseNumbers = ocwContentStorage.meta.client.list_objects(
                Bucket=ocwContentStorage.name, Prefix=departmentPath.get("Prefix"), Delimiter="/")
            for courseNumberPath in courseNumbers.get("CommonPrefixes"):
                courseTerms = ocwContentStorage.meta.client.list_objects(
                    Bucket=ocwContentStorage.name, Prefix=courseNumberPath.get("Prefix"), Delimiter="/")
                for courseTerm in courseTerms.get("CommonPrefixes"):
                    courseFolders = ocwContentStorage.meta.client.list_objects(
                        Bucket=ocwContentStorage.name, Prefix=courseTerm.get("Prefix"), Delimiter="/")
                    for courseFolder in courseFolders.get("CommonPrefixes"):
                        courseId = os.path.basename(
                            os.path.normpath(courseFolder.get("Prefix")))
                        if courseId in courses:
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
