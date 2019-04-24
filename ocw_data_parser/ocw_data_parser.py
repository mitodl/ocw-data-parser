import logging
from html.parser import HTMLParser
import os
import base64
from requests import get
import boto3
from .utils import update_file_location, get_binary_data, is_json, get_correct_path, load_json_file, safe_get, \
    find_all_values_for_key
import json
from smart_open import smart_open


log = logging.getLogger(__name__)


class CustomHTMLParser(HTMLParser):
    def __init__(self, output_list=None):
        HTMLParser.__init__(self)
        if output_list is None:
            self.output_list = []
        else:
            self.output_list = output_list

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.output_list.append(dict(attrs).get("href"))


class OCWParser(object):
    def __init__(self,
                 course_dir="",
                 destination_dir="",
                 loaded_jsons=list(),
                 upload_to_s3=False,
                 s3_bucket_name="",
                 s3_bucket_access_key="",
                 s3_bucket_secret_access_key="",
                 s3_target_folder=""):
        if not (course_dir and destination_dir) and not loaded_jsons:
            raise Exception("Message")
        self.course_dir = get_correct_path(course_dir) if course_dir else course_dir
        self.destination_dir = get_correct_path(destination_dir) if destination_dir else destination_dir
        self.upload_to_s3 = upload_to_s3
        self.s3_bucket_name = s3_bucket_name
        self.s3_bucket_access_key = s3_bucket_access_key
        self.s3_bucket_secret_access_key = s3_bucket_secret_access_key
        self.s3_target_folder = s3_target_folder
        self.media_jsons = []
        self.large_media_links = []
        self.course_image_uid = ""
        self.course_image_s3_link = ""
        self.course_image_alt_text = ""
        self.master_json = None
        if course_dir and destination_dir:
            # Preload raw jsons
            self.jsons = self.load_raw_jsons()
        else:
            self.jsons = loaded_jsons
        if self.jsons:
            self.master_json = self.generate_master_json()
            self.destination_dir += safe_get(self.jsons[0], "id") + "/"

    def get_master_json(self):
        return self.master_json

    def setup_s3_uploading(self, s3_bucket_name, s3_bucket_access_key, s3_bucket_secret_access_key, folder=""):
        self.upload_to_s3 = True
        self.s3_bucket_name = s3_bucket_name
        self.s3_bucket_access_key = s3_bucket_access_key
        self.s3_bucket_secret_access_key = s3_bucket_secret_access_key
        self.s3_target_folder = folder

    def load_raw_jsons(self):
        """ Loads all course raw jsons sequentially and returns them in an ordered list """
        dict_of_all_course_dirs = dict()
        for directory in os.listdir(self.course_dir):
            dir_in_question = self.course_dir + directory + "/"
            if os.path.isdir(dir_in_question):
                dict_of_all_course_dirs[directory] = []
                for file in os.listdir(dir_in_question):
                    if is_json(file):
                        # Turn file name to int to enforce sequential json loading later
                        dict_of_all_course_dirs[directory].append(int(file.split(".")[0]))
                dict_of_all_course_dirs[directory] = sorted(dict_of_all_course_dirs[directory])

        # Load JSONs into memory
        loaded_jsons = []
        for key, val in dict_of_all_course_dirs.items():
            path_to_subdir = self.course_dir + key + "/"
            for json_index in val:
                file_path = path_to_subdir + str(json_index) + ".json"
                loaded_json = load_json_file(file_path)
                if loaded_json:
                    # Add the json file name (used for error reporting)
                    loaded_json["actual_file_name"] = str(json_index) + ".json"
                    loaded_jsons.append(loaded_json)
                else:
                    log.error("Failed to load %s", file_path)

        return loaded_jsons

    def generate_master_json(self):
        """ Generates master JSON file for the course """
        if not self.jsons:
            self.jsons = self.load_raw_jsons()

        # Find "CourseHomeSection" JSON and extract chp_image value
        for j in self.jsons:
            classname = j.get("_classname", None)
            # CourseHomeSection for courses and SRHomePage is for resources
            if classname in ["CourseHomeSection", "SRHomePage"]:
                self.course_image_uid = j.get("chp_image")
        if not self.course_image_uid:
            log.error("Missing course thumbnail image")
        # Generate master JSON
        new_json = dict()
        new_json["uid"] = safe_get(self.jsons[0], "_uid")
        new_json["title"] = safe_get(self.jsons[0], "title")
        new_json["description"] = safe_get(self.jsons[1], "description")
        new_json["sort_as"] = safe_get(self.jsons[0], "sort_as")
        master_course = safe_get(self.jsons[0], "master_course_number")
        new_json["department_number"] = master_course.split('.')[0]
        new_json["master_course_number"] = master_course.split('.')[1]
        new_json["from_semester"] = safe_get(self.jsons[0], "from_semester")
        new_json["from_year"] = safe_get(self.jsons[0], "from_year")
        new_json["to_semester"] = safe_get(self.jsons[0], "to_semester")
        new_json["to_year"] = safe_get(self.jsons[0], "to_year")
        new_json["course_owner"] = safe_get(self.jsons[0], "course_owner")
        new_json["course_level"] = safe_get(self.jsons[0], "course_level")
        new_json["url"] = safe_get(self.jsons[0], "technical_location").split("ocw.mit.edu")[1]
        new_json["short_url"] = safe_get(self.jsons[0], "id")
        new_json["image_src"] = self.course_image_s3_link
        new_json["image_description"] = self.course_image_alt_text
        tags_strings = safe_get(self.jsons[0], "subject")
        tags = list()
        for tag in tags_strings:
            tags.append({"name": tag})
        new_json["tags"] = tags
        new_json["instructors"] = safe_get(self.jsons[0], "instructors")
        new_json["language"] = safe_get(self.jsons[0], "language")
        new_json["extra_course_number"] = safe_get(self.jsons[0], "linked_course_number")
        new_json["course_features"] = safe_get(self.jsons[0], "feature_requirements")
        new_json["course_collections"] = safe_get(self.jsons[0], "category_features")
        new_json["course_pages"] = self.compose_pages()
        new_json["course_files"] = self.compose_media()
        new_json["course_embedded_media"] = self.compose_embedded_media()
        new_json["course_foreign_files"] = self.gather_foreign_media()

        self.master_json = new_json
        return new_json

    def compose_pages(self):
        def _compose_page_dict(j):
            url_data = safe_get(j, "technical_location")
            if url_data:
                url_data = url_data.split("ocw.mit.edu")[1]
            page_dict = {
                "uid": safe_get(j, "_uid"),
                "parent_uid": safe_get(j, "parent_uid"),
                "title": safe_get(j, "title"),
                "text": safe_get(j, "text"),
                "url": url_data,
                "short_url": safe_get(j, "id"),
                "description": safe_get(j, "description"),
                "type": safe_get(j, "_type"),
            }
            if "media_location" in j and j["media_location"] and j["_content_type"] == "text/html":
                page_dict["youtube_id"] = j["media_location"]

            return page_dict

        if not self.jsons:
            self.jsons = self.load_raw_jsons()
        page_types = ["CourseHomeSection", "CourseSection", "DownloadSection", "ThisCourseAtMITSection"]
        pages = []
        for json_file in self.jsons:
            if json_file["_content_type"] == "text/html" and \
                    "technical_location" in json_file and json_file["technical_location"] \
                    and json_file["id"] != "page-not-found" and \
                    "_type" in json_file and json_file["_type"] in page_types:
                pages.append(_compose_page_dict(json_file))
        return pages

    def compose_media(self):
        def _compose_media_dict(j):
            return {
                "uid": safe_get(j, "_uid"),
                "parent_uid": safe_get(j, "parent_uid"),
                "title": safe_get(j, "title"),
                "caption": safe_get(j, "caption"),
                "file_type": safe_get(j, "_content_type"),
                "alt_text": safe_get(j, "alternate_text"),
                "credit": safe_get(j, "credit"),
                "platform_requirements": safe_get(j, "other_platform_requirements"),
                "description": safe_get(j, "description"),
            }

        if not self.jsons:
            self.jsons = self.load_raw_jsons()
        result = []
        all_media_types = find_all_values_for_key(self.jsons, "_content_type")
        for lj in self.jsons:
            if lj["_content_type"] in all_media_types:
                self.media_jsons.append(lj)  # Keep track of the jsons that contain media in case we want to extract
                result.append(_compose_media_dict(lj))
        return result

    def compose_embedded_media(self):
        linked_media_parents = dict()
        for j in self.jsons:
            if j and "inline_embed_id" in j and j["inline_embed_id"]:
                temp = {
                    "title": j["title"],
                    "uid": j["_uid"],
                    "parent_uid": j["parent_uid"],
                    "technical_location": j["technical_location"],
                    "id": j["id"],
                    "inline_embed_id": j["inline_embed_id"],
                    "embedded_media": [],
                }
                # Find all children of linked embedded media
                for child in self.jsons:
                    if child["parent_uid"] == j["_uid"]:
                        embedded_media = {
                            "uid": child["_uid"],
                            "parent_uid": child["parent_uid"],
                            "id": child["id"],
                            "title": child["title"]
                        }
                        if "media_location" in child and child["media_location"]:
                            embedded_media["media_info"] = child["media_location"]
                        if "technical_location" in child and child["technical_location"]:
                            embedded_media["technical_location"] = child["technical_location"]
                        temp["embedded_media"].append(embedded_media)
                linked_media_parents[j["inline_embed_id"]] = temp
        return linked_media_parents

    def gather_foreign_media(self):
        containing_keys = ['bottomtext', 'courseoutcomestext', 'description', 'image_caption_text', 'optional_text',
                           'text']
        for j in self.jsons:
            for key in containing_keys:
                if key in j and isinstance(j[key], str) and "/ans7870/" in j[key]:
                    p = CustomHTMLParser()
                    p.feed(j[key])
                    if p.output_list:
                        for link in p.output_list:
                            if link and "/ans7870/" in link and "." in link.split("/")[-1]:
                                obj = {
                                    "parent_uid": safe_get(j, "_uid"),
                                    "link": link
                                }
                                self.large_media_links.append(obj)
        return self.large_media_links

    def extract_media_locally(self):
        if not self.media_jsons:
            log.debug("You have to compose media for course first!")
            return

        path_to_containing_folder = self.destination_dir + "static_files/"
        os.makedirs(path_to_containing_folder, exist_ok=True)
        for j in self.media_jsons:
            filename = safe_get(j, "_uid") + "_" + safe_get(j, "id")
            d = get_binary_data(j)
            if d:
                with open(path_to_containing_folder + filename, "wb") as f:
                    data = base64.b64decode(d)
                    f.write(data)
                update_file_location(self.master_json, path_to_containing_folder + filename, safe_get(j, "_uid"))
                log.info("Extracted %s", filename)
            else:
                json_file = j["actual_file_name"]
                log.error("Media file %s without either datafield key", json_file)
        log.info("Done! extracted static media to %s", path_to_containing_folder)
        self.export_master_json()

    def extract_foreign_media_locally(self):
        if not self.large_media_links:
            log.debug("Your course has 0 foreign media files")
            return

        path_to_containing_folder = self.destination_dir + "static_files/"
        os.makedirs(path_to_containing_folder, exist_ok=True)
        for media in self.large_media_links:
            file_name = media["link"].split("/")[-1]
            with open(path_to_containing_folder + file_name, "wb") as file:
                response = get(media["link"])
                file.write(response.content)
            update_file_location(self.master_json, path_to_containing_folder + file_name)
            log.info("Extracted %s", file_name)
        log.info("Done! extracted foreign media to %s", path_to_containing_folder)
        self.export_master_json()

    def export_master_json(self):
        os.makedirs(self.destination_dir, exist_ok=True)
        with open(self.destination_dir + "master.json", "w") as file:
            json.dump(self.master_json, file)
        log.info("Extracted %s", self.destination_dir + 'master.json')

    def upload_all_media_to_s3(self, chunk_size=1000000, upload_master_json=False):
        # default chunk_size set to 10 megabytes
        if not self.s3_bucket_name:
            log.error("Please set your s3 bucket name")
            return

        bucket_base_url = f"https://{self.s3_bucket_name}.s3.amazonaws.com/"
        if self.s3_target_folder:
            if self.s3_target_folder[-1] != "/":
                self.s3_target_folder += "/"
            bucket_base_url += self.s3_target_folder

        s3_bucket = boto3.resource("s3",
                                   aws_access_key_id=self.s3_bucket_access_key,
                                   aws_secret_access_key=self.s3_bucket_secret_access_key
                                   ).Bucket(self.s3_bucket_name)
        # Upload static files first
        for file in self.media_jsons:
            uid = safe_get(file, "_uid")
            filename = uid + "_" + safe_get(file, "id")
            if not get_binary_data(file):
                log.error("Could not load binary data for file: %s", filename)
            else:
                d = base64.b64decode(get_binary_data(file))
            if d:
                s3_bucket.put_object(Key=self.s3_target_folder + filename, Body=d, ACL="public-read")
                update_file_location(self.master_json, bucket_base_url + filename, uid)
                log.info("Uploaded %s", filename)

                # Track course image link
                if self.course_image_uid and uid == self.course_image_uid:
                    self.course_image_s3_link = bucket_base_url + filename
                    self.course_image_alt_text = safe_get(file, "description")
                    self.master_json["image_src"] = self.course_image_s3_link
                    self.master_json["image_description"] = self.course_image_alt_text
            else:
                log.error("Could NOT upload %s", filename)

        # Upload foreign(large) media files:
        for media in self.large_media_links:
            filename = media["link"].split("/")[-1]
            response = get(media["link"], stream=True)
            if response:
                s3_uri = f"s3://{self.s3_bucket_access_key}:{self.s3_bucket_secret_access_key}@{self.s3_bucket_name}/"
                with smart_open(s3_uri + self.s3_target_folder + filename, "wb") as s3:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        s3.write(chunk)
                response.close()
                update_file_location(self.master_json, bucket_base_url + filename)
                log.info("Uploaded %s", filename)
            else:
                log.error("Could NOT upload %s", filename)

        if upload_master_json:
            uid = self.master_json.get('uid')
            if uid:
                s3_bucket.put_object(Key=self.s3_target_folder + f"{uid}_master.json",
                                     Body=json.dumps(self.master_json),
                                     ACL='private')
            else:
                log.error('No unique uid found for this master_json')

    def upload_course_image(self):
        if not self.s3_bucket_name:
            log.error("Please set your s3 bucket name")
            return
        bucket_base_url = f"https://{self.s3_bucket_name}.s3.amazonaws.com/"
        if self.s3_target_folder:
            if self.s3_target_folder[-1] != "/":
                self.s3_target_folder += "/"
            bucket_base_url += self.s3_target_folder

        s3_bucket = boto3.resource("s3",
                                   aws_access_key_id=self.s3_bucket_access_key,
                                   aws_secret_access_key=self.s3_bucket_secret_access_key
                                   ).Bucket(self.s3_bucket_name)
        # Upload static files first
        for file in self.media_jsons:
            uid = safe_get(file, "_uid")
            if uid == self.course_image_uid:
                filename = uid + "_" + safe_get(file, "id")
                image_binary_data = get_binary_data(file)
                if not image_binary_data:
                    log.error(filename)
                else:
                    d = base64.b64decode(image_binary_data)
                    s3_bucket.put_object(Key=self.s3_target_folder + filename, Body=d, ACL="public-read")
                    log.info("Uploaded %s", filename)
                    self.course_image_s3_link = bucket_base_url + filename
                    self.course_image_alt_text = safe_get(file, "description")
                    self.master_json["image_src"] = self.course_image_s3_link
                    self.master_json["image_description"] = self.course_image_alt_text
                    log.info("Uploaded %s", filename)
                break
