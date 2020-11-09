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
    def __init__(self):
        super().__init__()
        self.output_list = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.output_list.append(dict(attrs).get("href"))


def load_raw_jsons(course_dir):
    """ Loads all course raw jsons sequentially and returns them in an ordered list """
    dict_of_all_course_dirs = dict()
    for directory in os.listdir(course_dir):
        dir_in_question = course_dir + directory + "/"
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
        path_to_subdir = course_dir + key + "/"
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


def _compose_page_dict(json_file):
    url_data = json_file.get("technical_location")
    if url_data:
        url_data = url_data.split("ocw.mit.edu")[1]
    page_dict = {
        "order_index": json_file.get("order_index"),
        "uid": json_file.get("_uid"),
        "parent_uid": json_file.get("parent_uid"),
        "title": json_file.get("title"),
        "short_page_title": json_file.get("short_page_title"),
        "text": json_file.get("text"),
        "url": url_data,
        "short_url": json_file.get("id"),
        "description": json_file.get("description"),
        "type": json_file.get("_type"),
        "is_image_gallery": json_file.get("is_image_gallery"),
        "is_media_gallery": json_file.get("is_media_gallery"),
        "list_in_left_nav": json_file.get("list_in_left_nav"),
        "file_location": json_file.get("_uid") + "_" + json_file.get("id") + ".html",
        "bottomtext": json_file.get("bottomtext"),
    }
    if "media_location" in json_file and json_file["media_location"] and json_file["_content_type"] == "text/html":
        page_dict["youtube_id"] = json_file["media_location"]

    return page_dict


def compose_pages(jsons):
    page_types = ["CourseHomeSection", "CourseSection", "DownloadSection",
                  "ThisCourseAtMITSection", "SupplementalResourceSection"]
    pages = []
    for json_file in jsons:
        if json_file["_content_type"] == "text/html" and \
                "technical_location" in json_file and json_file["technical_location"] \
                and json_file["id"] != "page-not-found" and \
                "_type" in json_file and json_file["_type"] in page_types:
            pages.append(_compose_page_dict(json_file))
    return pages


def _compose_media_dict(media_json):
    return {
        "order_index": media_json.get("order_index"),
        "uid": media_json.get("_uid"),
        "id": media_json.get("id"),
        "parent_uid": media_json.get("parent_uid"),
        "title": media_json.get("title"),
        "caption": media_json.get("caption"),
        "file_type": media_json.get("_content_type"),
        "alt_text": media_json.get("alternate_text"),
        "credit": media_json.get("credit"),
        "platform_requirements": media_json.get("other_platform_requirements"),
        "description": media_json.get("description"),
        "type": media_json.get("_type"),
    }


def compose_media(jsons):
    media_jsons = []
    all_media_types = find_all_values_for_key(jsons, "_content_type")
    for json_file in jsons:
        if json_file["_content_type"] in all_media_types:
            # Keep track of the jsons that contain media in case we want to extract
            media_jsons.append(json_file)

    return [_compose_media_dict(media_json) for media_json in media_jsons], media_jsons


def compose_embedded_media(jsons):
    linked_media_parents = dict()
    for json_file in jsons:
        if json_file and "inline_embed_id" in json_file and json_file["inline_embed_id"]:
            temp = {
                "order_index": json_file.get("order_index"),
                "title": json_file["title"],
                "uid": json_file["_uid"],
                "parent_uid": json_file["parent_uid"],
                "technical_location": json_file["technical_location"],
                "short_url": json_file["id"],
                "inline_embed_id": json_file["inline_embed_id"],
                "about_this_resource_text": json_file["about_this_resource_text"],
                "related_resources_text": json_file["related_resources_text"],
                "transcript": json_file["transcript"],
                "embedded_media": []
            }
            # Find all children of linked embedded media
            for child in jsons:
                if child["parent_uid"] == json_file["_uid"]:
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
            linked_media_parents[json_file["inline_embed_id"]] = temp
    return linked_media_parents


def compose_course_features(jsons, course_pages):
    course_features = {}
    feature_requirements = jsons[0].get("feature_requirements")
    if feature_requirements:
        for feature_requirement in feature_requirements:
            for page in course_pages:
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
    return list(course_features.values())


def gather_foreign_media(jsons):
    containing_keys = ['bottomtext', 'courseoutcomestext', 'description', 'image_caption_text', 'optional_text',
                       'text']
    large_media_links = []
    for j in jsons:
        for key in containing_keys:
            if key in j and isinstance(j[key], str) and "/ans7870/" in j[key]:
                p = CustomHTMLParser()
                p.feed(j[key])
                if p.output_list:
                    for link in p.output_list:
                        if link and "/ans7870/" in link and "." in link.split("/")[-1]:
                            obj = {
                                "parent_uid": j.get("_uid"),
                                "link": link.strip()
                            }
                            large_media_links.append(obj)
    return large_media_links


def compose_open_learning_library_related(jsons):
    open_learning_library_related = []
    courselist_features = jsons[0].get("courselist_features")
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
    return open_learning_library_related


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
                 beautify_parsed_json=False):
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
        self.parsed_json = None
        if course_dir and destination_dir:
            # Preload raw jsons
            self.jsons = load_raw_jsons(self.course_dir)
        else:
            self.jsons = loaded_jsons
        if self.jsons:
            self.parsed_json = self.generate_parsed_json()
            self.destination_dir += self.jsons[0].get("id") + "/"
        self.beautify_parsed_json = beautify_parsed_json

    def get_parsed_json(self):
        return self.parsed_json

    def setup_s3_uploading(self, s3_bucket_name, s3_bucket_access_key, s3_bucket_secret_access_key, folder=""):
        self.upload_to_s3 = True
        self.s3_bucket_name = s3_bucket_name
        self.s3_bucket_access_key = s3_bucket_access_key
        self.s3_bucket_secret_access_key = s3_bucket_secret_access_key
        self.s3_target_folder = folder

    def generate_parsed_json(self):
        """ Generates parsed JSON file for the course """
        if not self.jsons:
            self.jsons = load_raw_jsons(self.course_dir)

        # Find "CourseHomeSection" JSON and extract chp_image value
        for j in self.jsons:
            classname = j.get("_classname", None)
            # CourseHomeSection for courses and SRHomePage is for resources
            if classname in ["CourseHomeSection", "SRHomePage"]:
                self.course_image_uid = j.get("chp_image")
                self.course_thumbnail_image_uid = j.get("chp_image_thumb")

        master_course = self.jsons[0].get("master_course_number")
        technical_location = self.jsons[0].get("technical_location")
        instructors = self.jsons[0].get("instructors")
        course_pages = compose_pages(self.jsons)
        course_files, self.media_jsons = compose_media(self.jsons)
        foreign_media = gather_foreign_media(self.jsons)
        self.large_media_links = foreign_media

        # Generate parsed JSON
        new_json = {
            "uid": self.jsons[0].get("_uid"),
            "title": self.jsons[0].get("title"),
            "description": self.jsons[1].get("description"),
            "other_information_text": self.jsons[1].get("other_information_text"),
            "first_published_to_production": self.jsons[0].get("first_published_to_production"),
            "last_published_to_production": self.jsons[0].get("last_published_to_production"),
            "last_unpublishing_date": self.jsons[0].get("last_unpublishing_date"),
            "retirement_date": self.jsons[0].get("retirement_date"),
            "sort_as": self.jsons[0].get("sort_as"),
            "department_number": master_course.split('.')[0] if master_course else "",
            "master_course_number": master_course.split('.')[1] if master_course else "",
            "other_version_parent_uids": self.jsons[0].get("master_subject"),
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
            "tags": [{"name": tag} for tag in self.jsons[0].get("subject")],
            "instructors": [
                {key: value for key, value in instructor.items() if key != 'mit_id'}
                 for instructor in instructors if instructors
            ],
            "language": self.jsons[0].get("language"),
            "extra_course_number": self.jsons[0].get("linked_course_number"),
            "course_collections": self.jsons[0].get("category_features"),
            "course_pages": course_pages,
            "course_features": compose_course_features(self.jsons, course_pages),
            "course_files": course_files,
            "course_embedded_media": compose_embedded_media(self.jsons),
            "course_foreign_files": foreign_media,
            "open_learning_library_related": compose_open_learning_library_related(self.jsons),
        }

        self.parsed_json = new_json
        return new_json

    def extract_media_locally(self):
        if not self.media_jsons:
            log.debug("You have to compose media for course first!")
            return

        path_to_containing_folder = self.destination_dir + "output/" + self.static_prefix \
            if self.static_prefix else self.destination_dir + "output/static_files/"
        url_path_to_media = self.static_prefix if self.static_prefix else path_to_containing_folder
        os.makedirs(path_to_containing_folder, exist_ok=True)
        for page in compose_pages(self.jsons):
            filename, html = htmlify(page)
            if filename and html:
                with open(path_to_containing_folder + filename, "w") as f:
                    f.write(html)
        for media_json in self.media_jsons:
            file_name = media_json.get("_uid") + "_" + media_json.get("id")
            d = get_binary_data(media_json)
            if d:
                with open(path_to_containing_folder + file_name, "wb") as f:
                    data = base64.b64decode(d)
                    f.write(data)
                update_file_location(
                    self.parsed_json, url_path_to_media + file_name, media_json.get("_uid"))
                log.info("Extracted %s", file_name)
            else:
                json_file = media_json["actual_file_name"]
                log.error(
                    "Media file %s without either datafield key", json_file)
        log.info("Done! extracted static media to %s",
                 path_to_containing_folder)
        self.export_parsed_json()

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
                self.parsed_json, url_path_to_media + file_name)
            log.info("Extracted %s", file_name)
        log.info("Done! extracted foreign media to %s",
                 path_to_containing_folder)
        self.export_parsed_json()

    def export_parsed_json(self, s3_links=False, upload_parsed_json=False):
        if s3_links:
            self.upload_all_media_to_s3(upload_parsed_json=upload_parsed_json)
        os.makedirs(self.destination_dir, exist_ok=True)
        file_path = os.path.join(self.destination_dir, "{}_parsed.json".format(self.parsed_json["short_url"]))
        with open(file_path, "w") as json_file:
            if self.beautify_parsed_json:
                json.dump(self.parsed_json, json_file, sort_keys=True, indent=4)
            else:
                json.dump(self.parsed_json, json_file)
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
                    self.parsed_json["image_src"] = self.course_image_s3_link
                    self.parsed_json["image_description"] = self.course_image_alt_text

                if self.course_thumbnail_image_uid and uid == self.course_thumbnail_image_uid:
                    self.course_thumbnail_image_s3_link = bucket_base_url + filename
                    self.course_thumbnail_image_alt_text = file.get("description")
                    self.parsed_json["thumbnail_image_src"] = self.course_thumbnail_image_s3_link
                    self.parsed_json["thumbnail_image_description"] = self.course_thumbnail_image_alt_text

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
                for p in compose_pages(self.jsons):
                    filename, html = htmlify(p)
                    if filename and html:
                        if upload_to_s3:
                            s3_bucket.put_object(
                                Key=self.s3_target_folder + filename, Body=html, ACL="public-read")
                        update_file_location(
                            self.parsed_json, bucket_base_url + filename, p.get("uid"))
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
                            self.parsed_json.get("short_url")
                        )
                        continue
                    else:
                        d = base64.b64decode(get_binary_data(file))
                    if upload_to_s3 and d:
                        s3_bucket.put_object(
                            Key=self.s3_target_folder + filename, Body=d, ACL="public-read")
                    update_file_location(
                        self.parsed_json, bucket_base_url + filename, uid)
                    if self.course_image_uid and uid == self.course_image_uid:
                        self.course_image_s3_link = bucket_base_url + filename
                        self.course_image_alt_text = file.get("description")
                        self.parsed_json["image_src"] = self.course_image_s3_link
                        self.parsed_json["image_description"] = self.course_image_alt_text

                    if self.course_thumbnail_image_uid and uid == self.course_thumbnail_image_uid:
                        self.course_thumbnail_image_s3_link = bucket_base_url + filename
                        self.course_thumbnail_image_alt_text = file.get("description")
                        self.parsed_json["thumbnail_image_src"] = self.course_thumbnail_image_s3_link
                        self.parsed_json["thumbnail_image_description"] = self.course_thumbnail_image_alt_text
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
                            self.parsed_json, bucket_base_url + filename)
                        log.info("Uploaded %s", filename)
                    else:
                        log.error("Could NOT upload %s for course %s", filename, self.parsed_json.get("short_url"))
                    update_file_location(
                        self.parsed_json, bucket_base_url + filename)

    def upload_all_media_to_s3(self, upload_parsed_json=False):
        self.update_s3_content()
        if upload_parsed_json:
            s3_bucket = self.get_s3_bucket()
            self.upload_parsed_json_to_s3(s3_bucket)

    def upload_parsed_json_to_s3(self, s3_bucket):
        short_url = self.parsed_json.get('short_url')
        if short_url:
            s3_bucket.put_object(Key=self.s3_target_folder + f"{short_url}_parsed.json",
                                 Body=json.dumps(self.parsed_json),
                                 ACL='private')
        else:
            log.error("No short_url found in parsed_json")

    def upload_course_image(self):
        s3_bucket = self.get_s3_bucket()
        self.update_s3_content(upload=False)
        for file in self.media_jsons:
            uid = file.get("_uid")
            if uid == self.course_image_uid or uid == self.course_thumbnail_image_uid:
                self.update_s3_content(
                    update_pages=False, update_external_media=False, media_uid_filter=[uid])
        self.upload_parsed_json_to_s3(s3_bucket)
