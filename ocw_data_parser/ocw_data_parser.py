import logging
from html.parser import HTMLParser
import os
import copy
import shutil
import base64
from requests import get
import boto3
from ocw_data_parser.utils import update_file_location, get_binary_data, is_json, get_correct_path, load_json_file, \
    find_all_values_for_key, htmlify
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
                 static_prefix="",
                 loaded_jsons=None,
                 upload_to_s3=False,
                 s3_bucket_name="",
                 s3_bucket_access_key="",
                 s3_bucket_secret_access_key="",
                 s3_target_folder="",
                 beautify_master_json=False):
        if not (course_dir and destination_dir) and not loaded_jsons:
            raise Exception(
                "OCWParser must be initated with course_dir and destination_dir or loaded_jsons")

        if loaded_jsons is None:
            loaded_jsons = []

        self.course_dir = get_correct_path(
            course_dir) if course_dir else course_dir
        self.destination_dir = get_correct_path(
            destination_dir) if destination_dir else destination_dir
        self.static_prefix = static_prefix
        self.upload_to_s3 = upload_to_s3
        self.s3_bucket_name = s3_bucket_name
        self.s3_bucket_access_key = s3_bucket_access_key
        self.s3_bucket_secret_access_key = s3_bucket_secret_access_key
        self.s3_target_folder = s3_target_folder
        self.media_jsons = []
        self.large_media_links = []
        self.course_image_uid = ""
        self.course_thumbnail_image_uid = ""
        self.course_image_s3_link = ""
        self.course_thumbnail_image_s3_link = ""
        self.course_image_alt_text = ""
        self.course_thumbnail_image_alt_text = ""
        self.master_json = None
        if course_dir and destination_dir:
            # Preload raw jsons
            self.jsons = self.load_raw_jsons()
        else:
            self.jsons = loaded_jsons
        if self.jsons:
            self.master_json = self.generate_master_json()
            self.destination_dir += self.jsons[0].get("id") + "/"
        self.beautify_master_json = beautify_master_json

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
                        dict_of_all_course_dirs[directory].append(
                            int(file.split(".")[0]))
                dict_of_all_course_dirs[directory] = sorted(
                    dict_of_all_course_dirs[directory])

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
                    # The only representation we have of ordering is the file name
                    loaded_json["order_index"] = int(json_index)
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
                self.course_thumbnail_image_uid = j.get("chp_image_thumb")

        master_course = self.jsons[0].get("master_course_number")
        technical_location = self.jsons[0].get("technical_location")

        # Generate master JSON
        new_json = {
            "uid": self.jsons[0].get("_uid"),
            "title": self.jsons[0].get("title"),
            "description": self.jsons[1].get("description"),
            "other_information_text": self.jsons[1].get("other_information_text"),
            "last_published_to_production": self.jsons[0].get("last_published_to_production"),
            "last_unpublishing_date": self.jsons[0].get("last_unpublishing_date"),
            "retirement_date": self.jsons[0].get("retirement_date"),
            "sort_as": self.jsons[0].get("sort_as"),
            "department_number": master_course.split('.')[0] if master_course else "",
            "master_course_number": master_course.split('.')[1] if master_course else "",
            "from_semester": self.jsons[0].get("from_semester"),
            "from_year": self.jsons[0].get("from_year"),
            "to_semester": self.jsons[0].get("to_semester"),
            "to_year": self.jsons[0].get("to_year"),
            "course_level": self.jsons[0].get("course_level"),
            "url": technical_location.split("ocw.mit.edu")[1] if technical_location else "",
            "short_url": self.jsons[0].get("id"),
            "image_src": self.course_image_s3_link,
            "thumbnail_image_src": self.course_thumbnail_image_s3_link,
            "image_description": self.course_image_alt_text,
            "thumbnail_image_description": self.course_thumbnail_image_alt_text,
            "image_alternate_text": self.jsons[1].get("image_alternate_text"),
            "image_caption_text": self.jsons[1].get("image_caption_text"),
        }
        tags_strings = self.jsons[0].get("subject")
        tags = list()
        for tag in tags_strings:
            tags.append({"name": tag})
        new_json["tags"] = tags
        instructors = self.jsons[0].get("instructors")
        new_json["instructors"] = [
            {key: value for key, value in instructor.items() if key != 'mit_id'}
             for instructor in instructors if instructors
        ]
        new_json["language"] = self.jsons[0].get("language")
        new_json["extra_course_number"] = self.jsons[0].get("linked_course_number")
        new_json["course_collections"] = self.jsons[0].get("category_features")
        new_json["course_pages"] = self.compose_pages()
        course_features = {}
        feature_requirements = self.jsons[0].get("feature_requirements")
        if feature_requirements:
            for feature_requirement in feature_requirements:
                for page in new_json["course_pages"]:
                    ocw_feature_url = feature_requirement.get("ocw_feature_url")
                    if ocw_feature_url:
                        ocw_feature_url_parts = ocw_feature_url.split("/")
                        ocw_feature_short_url = ocw_feature_url
                        if len(ocw_feature_url_parts) > 1:
                            ocw_feature_short_url = ocw_feature_url_parts[-2] + \
                                "/" + ocw_feature_url_parts[-1]
                        if page["short_url"] in ocw_feature_short_url and 'index.htm' not in page["short_url"]:
                            course_feature = copy.copy(feature_requirement)
                            course_feature["ocw_feature_url"] = './resolveuid/' + page["uid"]
                            course_features[page["uid"]] = course_feature
        new_json["course_features"] = list(course_features.values())
        open_learning_library_related = []
        courselist_features = self.jsons[0].get("courselist_features")
        if courselist_features:
            for courselist_feature in courselist_features:
                if courselist_feature["ocw_feature"] == "Open Learning Library":
                    raw_url = courselist_feature["ocw_feature_url"]
                    courses_and_links = raw_url.split(",")
                    for course_and_link in courses_and_links:
                        related_course = {}
                        course, url = course_and_link.strip().split("::")
                        related_course["course"] = course
                        related_course["url"] = url
                        open_learning_library_related.append(related_course)
        new_json["open_learning_library_related"] = open_learning_library_related
        new_json["course_files"] = self.compose_media()
        new_json["course_embedded_media"] = self.compose_embedded_media()
        new_json["course_foreign_files"] = self.gather_foreign_media()

        self.master_json = new_json
        return new_json

    def compose_pages(self):
        def _compose_page_dict(j):
            url_data = j.get("technical_location")
            if url_data:
                url_data = url_data.split("ocw.mit.edu")[1]
            page_dict = {
                "order_index": j.get("order_index"),
                "uid": j.get("_uid"),
                "parent_uid": j.get("parent_uid"),
                "title": j.get("title"),
                "short_page_title": j.get("short_page_title"),
                "text": j.get("text"),
                "bottomtext": j.get("bottomtext"),
                "url": url_data,
                "short_url": j.get("id"),
                "description": j.get("description"),
                "type": j.get("_type"),
                "is_image_gallery": j.get("is_image_gallery"),
                "is_media_gallery": j.get("is_media_gallery"),
                "list_in_left_nav": j.get("list_in_left_nav"),
                "file_location": j.get("_uid") + "_" + j.get("id") + ".html"
            }
            if "media_location" in j and j["media_location"] and j["_content_type"] == "text/html":
                page_dict["youtube_id"] = j["media_location"]

            return page_dict

        if not self.jsons:
            self.jsons = self.load_raw_jsons()
        page_types = ["CourseHomeSection", "CourseSection", "DownloadSection",
                      "ThisCourseAtMITSection", "SupplementalResourceSection"]
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
                "order_index": j.get("order_index"),
                "uid": j.get("_uid"),
                "id": j.get("id"),
                "parent_uid": j.get("parent_uid"),
                "title": j.get("title"),
                "caption": j.get("caption"),
                "file_type": j.get("_content_type"),
                "alt_text": j.get("alternate_text"),
                "credit": j.get("credit"),
                "platform_requirements": j.get("other_platform_requirements"),
                "description": j.get("description"),
                "type": j.get("_type"),
            }

        if not self.jsons:
            self.jsons = self.load_raw_jsons()
        result = []
        all_media_types = find_all_values_for_key(self.jsons, "_content_type")
        for lj in self.jsons:
            if lj["_content_type"] in all_media_types:
                # Keep track of the jsons that contain media in case we want to extract
                self.media_jsons.append(lj)
                result.append(_compose_media_dict(lj))
        return result

    def compose_embedded_media(self):
        linked_media_parents = dict()
        for j in self.jsons:
            if j and "inline_embed_id" in j and j["inline_embed_id"]:
                temp = {
                    "order_index": j.get("order_index"),
                    "title": j["title"],
                    "uid": j["_uid"],
                    "parent_uid": j["parent_uid"],
                    "technical_location": j["technical_location"],
                    "short_url": j["id"],
                    "inline_embed_id": j["inline_embed_id"],
                    "about_this_resource_text": j["about_this_resource_text"],
                    "related_resources_text": j["related_resources_text"],
                    "transcript": j["transcript"],
                    "embedded_media": []
                }
                # Find all children of linked embedded media
                for child in self.jsons:
                    if child["parent_uid"] == j["_uid"]:
                        embedded_media = {
                            "uid": child["_uid"],
                            "parent_uid": child["parent_uid"],
                            "id": child["id"],
                            "title": child["title"],
                            "type": child.get("media_asset_type")
                        }
                        if "media_location" in child and child["media_location"]:
                            embedded_media["media_location"] = child["media_location"]
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
                                    "parent_uid": j.get("_uid"),
                                    "link": link
                                }
                                self.large_media_links.append(obj)
        return self.large_media_links

    def extract_media_locally(self):
        if not self.media_jsons:
            log.debug("You have to compose media for course first!")
            return

        path_to_containing_folder = self.destination_dir + "output/" + self.static_prefix \
            if self.static_prefix else self.destination_dir + "output/static_files/"
        url_path_to_media = self.static_prefix if self.static_prefix else path_to_containing_folder
        os.makedirs(path_to_containing_folder, exist_ok=True)
        for p in self.compose_pages():
            filename, html = htmlify(p)
            if filename and html:
                with open(path_to_containing_folder + filename, "w") as f:
                    f.write(html)
        for j in self.media_jsons:
            file_name = j.get("_uid") + "_" + j.get("id")
            d = get_binary_data(j)
            if d:
                with open(path_to_containing_folder + file_name, "wb") as f:
                    data = base64.b64decode(d)
                    f.write(data)
                update_file_location(
                    self.master_json, url_path_to_media + file_name, j.get("_uid"))
                log.info("Extracted %s", file_name)
            else:
                json_file = j["actual_file_name"]
                log.error(
                    "Media file %s without either datafield key", json_file)
        log.info("Done! extracted static media to %s",
                 path_to_containing_folder)
        self.export_master_json()

    def extract_foreign_media_locally(self):
        if not self.large_media_links:
            log.debug("Your course has 0 foreign media files")
            return

        path_to_containing_folder = self.destination_dir + 'output/' + self.static_prefix \
            if self.static_prefix else self.destination_dir + "output/static_files/"
        url_path_to_media = self.static_prefix if self.static_prefix else path_to_containing_folder
        os.makedirs(path_to_containing_folder, exist_ok=True)
        for media in self.large_media_links:
            file_name = media["link"].split("/")[-1]
            with open(path_to_containing_folder + file_name, "wb") as file:
                response = get(media["link"])
                file.write(response.content)
            update_file_location(
                self.master_json, url_path_to_media + file_name)
            log.info("Extracted %s", file_name)
        log.info("Done! extracted foreign media to %s",
                 path_to_containing_folder)
        self.export_master_json()

    def export_master_json(self, s3_links=False):
        if s3_links:
            self.update_s3_content()
        os.makedirs(self.destination_dir + "master/", exist_ok=True)
        file_path = self.destination_dir + "master/master.json"
        with open(file_path, "w") as file:
            if self.beautify_master_json:
                json.dump(self.master_json, file, sort_keys=True, indent=4)
            else:
                json.dump(self.master_json, file)
        log.info("Extracted %s", file_path)

    def find_course_image_s3_link(self):
        bucket_base_url = self.get_s3_base_url()
        if bucket_base_url:
            for file in self.media_jsons:
                uid = file.get("_uid")
                filename = uid + "_" + file.get("id")
                if self.course_image_uid and uid == self.course_image_uid:
                    self.course_image_s3_link = bucket_base_url + filename
                    self.course_image_alt_text = file.get("description")
                    self.master_json["image_src"] = self.course_image_s3_link
                    self.master_json["image_description"] = self.course_image_alt_text

                if self.course_thumbnail_image_uid and uid == self.course_thumbnail_image_uid:
                    self.course_thumbnail_image_s3_link = bucket_base_url + filename
                    self.course_thumbnail_image_alt_text = file.get("description")
                    self.master_json["thumbnail_image_src"] = self.course_thumbnail_image_s3_link
                    self.master_json["thumbnail_image_description"] = self.course_thumbnail_image_alt_text

    def get_s3_base_url(self):
        if not self.s3_bucket_name:
            log.error("Please set your s3 bucket name")
            return
        bucket_base_url = f"https://{self.s3_bucket_name}.s3.amazonaws.com/"
        if self.s3_target_folder:
            if self.s3_target_folder[-1] != "/":
                self.s3_target_folder += "/"
            bucket_base_url += self.s3_target_folder
        return bucket_base_url

    def get_s3_bucket(self):
        self.find_course_image_s3_link()
        return boto3.resource("s3",
                              aws_access_key_id=self.s3_bucket_access_key,
                              aws_secret_access_key=self.s3_bucket_secret_access_key
                              ).Bucket(self.s3_bucket_name)

    def update_s3_content(self, upload=None, update_pages=True, update_media=True, media_uid_filter=None, update_external_media=True, chunk_size=1000000):
        upload_to_s3 = self.upload_to_s3
        if upload:
            upload_to_s3 = upload
        bucket_base_url = self.get_s3_base_url()
        if bucket_base_url:
            s3_bucket = self.get_s3_bucket()
            if update_pages:
                for p in self.compose_pages():
                    filename, html = htmlify(p)
                    if filename and html:
                        if upload_to_s3:
                            s3_bucket.put_object(
                                Key=self.s3_target_folder + filename, Body=html, ACL="public-read")
                        update_file_location(
                            self.master_json, bucket_base_url + filename, p.get("uid"))
            if update_media:
                if media_uid_filter:
                    media_jsons = [
                        media_json for media_json in self.media_jsons if media_json in media_uid_filter]
                else:
                    media_jsons = self.media_jsons
                for file in media_jsons:
                    uid = file.get("_uid")
                    filename = uid + "_" + file.get("id")
                    if not get_binary_data(file):
                        log.error(
                            "Could not load binary data for file %s in json file %s for course %s",
                            filename,
                            file.get("actual_file_name"),
                            self.master_json.get("short_url")
                        )
                        continue
                    else:
                        d = base64.b64decode(get_binary_data(file))
                    if upload_to_s3 and d:
                        s3_bucket.put_object(
                            Key=self.s3_target_folder + filename, Body=d, ACL="public-read")
                    update_file_location(
                        self.master_json, bucket_base_url + filename, uid)
                    if self.course_image_uid and uid == self.course_image_uid:
                        self.course_image_s3_link = bucket_base_url + filename
                        self.course_image_alt_text = file.get("description")
                        self.master_json["image_src"] = self.course_image_s3_link
                        self.master_json["image_description"] = self.course_image_alt_text

                    if self.course_thumbnail_image_uid and uid == self.course_thumbnail_image_uid:
                        self.course_thumbnail_image_s3_link = bucket_base_url + filename
                        self.course_thumbnail_image_alt_text = file.get("description")
                        self.master_json["thumbnail_image_src"] = self.course_thumbnail_image_s3_link
                        self.master_json["thumbnail_image_description"] = self.course_thumbnail_image_alt_text
            if update_external_media:
                for media in self.large_media_links:
                    filename = media["link"].split("/")[-1]
                    response = get(media["link"], stream=True)
                    if upload_to_s3 and response:
                        s3_uri = f"s3://{self.s3_bucket_access_key}:{self.s3_bucket_secret_access_key}@{self.s3_bucket_name}/"
                        with smart_open(s3_uri + self.s3_target_folder + filename, "wb") as s3:
                            for chunk in response.iter_content(chunk_size=chunk_size):
                                s3.write(chunk)
                        response.close()
                        update_file_location(
                            self.master_json, bucket_base_url + filename)
                        log.info("Uploaded %s", filename)
                    else:
                        log.error("Could NOT upload %s for course %s", filename, self.master_json.get("short_url"))
                    update_file_location(
                        self.master_json, bucket_base_url + filename)

    def upload_all_media_to_s3(self, upload_master_json=False):
        s3_bucket = self.get_s3_bucket()
        self.update_s3_content()
        if upload_master_json:
            self.upload_master_json_to_s3(s3_bucket)

    def upload_master_json_to_s3(self, s3_bucket):
        uid = self.master_json.get('uid')
        if uid:
            s3_bucket.put_object(Key=self.s3_target_folder + f"{uid}_master.json",
                                 Body=json.dumps(self.master_json),
                                 ACL='private')
        else:
            log.error("No unique uid found for master_json for course %s", self.master_json.get("short_url"))

    def upload_course_image(self):
        s3_bucket = self.get_s3_bucket()
        self.update_s3_content(upload=False)
        for file in self.media_jsons:
            uid = file.get("_uid")
            if uid == self.course_image_uid or uid == self.course_thumbnail_image_uid:
                self.update_s3_content(
                    update_pages=False, update_external_media=False, media_uid_filter=[uid])
        self.upload_master_json_to_s3(s3_bucket)
