"""OCWParser and related functions"""

import copy
from html.parser import HTMLParser
import json
import logging
import os
from pathlib import Path
from urllib.parse import urljoin

import boto3
import requests
from smart_open import smart_open

from ocw_data_parser.utils import (
    course_page_from_relative_url,
    update_file_location,
    get_binary_data,
    find_all_values_for_key,
    htmlify,
    convert_to_vtt,
)
from ocw_data_parser.course_feature_tags import match_course_feature_tag

log = logging.getLogger(__name__)


def _get(obj, key):
    """
    Retrieve an item from a dictionary, converting "None" to None if necessary

    Args:
        obj (dict): A dict
        key (str): A key in the dictionary

    Returns:
        any: The value at that key
    """
    value = obj.get(key)
    if value == "None":
        return None
    return value


class CustomHTMLParser(HTMLParser):
    """Capture links from an HTML file"""

    def __init__(self):
        super().__init__()
        self.output_list = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.output_list.append(dict(attrs).get("href"))

    def error(self, message):
        """Raise parsing errors"""
        raise Exception(message)


def load_raw_jsons(course_dir):
    """
    Loads all course raw jsons sequentially and returns them in an ordered list

    Args:
        course_dir (str or Path): Course directory path

    Returns:
        list of dict:
            The JSON from the course sorted by order index
    """
    course_dir = Path(course_dir)
    dict_of_all_course_dirs = dict()
    for dir_in_question in course_dir.iterdir():
        if dir_in_question.is_dir():
            dict_of_all_course_dirs[dir_in_question.name] = []
            for file in dir_in_question.iterdir():
                if file.suffix == ".json":
                    # Turn file name to int to enforce sequential json loading later
                    dict_of_all_course_dirs[dir_in_question.name].append(int(file.stem))
            dict_of_all_course_dirs[dir_in_question.name] = sorted(
                dict_of_all_course_dirs[dir_in_question.name]
            )

    # Load JSONs into memory
    loaded_jsons = []
    for key, val in dict_of_all_course_dirs.items():
        path_to_subdir = course_dir / key
        for json_index in val:
            file_path = path_to_subdir / f"{json_index}.json"
            with open(file_path) as file:
                loaded_json = json.load(file)
            # Add the json file name (used for error reporting)
            loaded_json["actual_file_name"] = f"{json_index}.json"
            # The only representation we have of ordering is the file name
            loaded_json["order_index"] = int(json_index)
            loaded_jsons.append(loaded_json)

    loaded_jsons = sorted(loaded_jsons, key=lambda d: d["order_index"])
    return loaded_jsons


def _compose_page_dict(json_file):
    instructor_insights_sections = [
        "courseoverviewtext",
        "courseoutcomestext",
        "instructorinsightstext",
        "curriculuminformationtext",
        "theclassroomtext",
        "studentinformationtext",
        "howstudenttimewasspenttext",
        "courseteamrolestext",
        "bottomtext",
    ]
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
    # handle divided instructor insights pages
    if page_dict["short_page_title"] == "Instructor Insights":
        first_level_keys = json_file.keys()
        for section in instructor_insights_sections:
            if section in first_level_keys:
                page_dict["text"] += json_file.get(section) + "\n"
    if (
        "media_location" in json_file
        and json_file["media_location"]
        and json_file["_content_type"] == "text/html"
    ):
        page_dict["youtube_id"] = json_file["media_location"]

    return page_dict


def compose_pages(jsons):
    """
    Create page dicts from course JSONs

    Args:
        jsons (list of dict): Course input

    Returns:
        list of dict:
            Course page information
    """
    page_types = [
        "CourseHomeSection",
        "SRHomePage",
        "CourseSection",
        "DownloadSection",
        "ThisCourseAtMITSection",
        "SupplementalResourceSection",
    ]
    pages = []
    for json_file in jsons:
        if (  # pylint: disable=too-many-boolean-expressions
            (
                json_file["_content_type"] == "text/html"
                or json_file["_content_type"] == "text/plain"
            )
            and "technical_location" in json_file
            and json_file["technical_location"]
            and json_file["id"] != "page-not-found"
            and "_type" in json_file
            and json_file["_type"] in page_types
        ):
            pages.append(_compose_page_dict(json_file))
    return pages


def _compose_media_dict(media_json, bucket_base_url):
    uid = media_json.get("_uid")
    file_name = media_json.get("id")
    if not file_name.startswith(uid):
        file_name = "{}_{}".format(uid, file_name)
    if bucket_base_url:
        file_location = urljoin(bucket_base_url, file_name)
    else:
        file_location = file_name
    media_dict = {
        "order_index": media_json.get("order_index"),
        "uid": uid,
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
        "file_location": file_location,
    }
    return media_dict


def compose_media(jsons, bucket_base_url):
    """
    Create media dicts from course JSONs

    Args:
        jsons (list of dict): Input from a course
        bucket_base_url (str): Base URL to use for the filename

    Returns:
        list of dict: The media dicts from the course
    """
    media_jsons = []
    all_media_types = find_all_values_for_key(jsons, "_content_type")
    for json_file in jsons:
        if json_file["_content_type"] in all_media_types:
            # Keep track of the jsons that contain media in case we want to extract
            media_jsons.append(json_file)

    return [
        _compose_media_dict(media_json, bucket_base_url) for media_json in media_jsons
    ], media_jsons


def compose_embedded_media(jsons):
    """
    Create dicts for embedded media from course JSONs

    Args:
        jsons (list of dict): Course input

    Returns:
        list of dict: Embedded media info
    """
    linked_media_parents = dict()
    for json_file in jsons:
        if (
            json_file
            and "inline_embed_id" in json_file
            and json_file["inline_embed_id"]
        ):
            temp = {
                "order_index": json_file.get("order_index"),
                "title": json_file["title"],
                "template_type": json_file["template_type"],
                "uid": json_file["_uid"],
                "parent_uid": json_file["parent_uid"],
                "technical_location": json_file["technical_location"],
                "short_url": json_file["id"],
                "inline_embed_id": json_file["inline_embed_id"],
                "about_this_resource_text": json_file["about_this_resource_text"],
                "related_resources_text": json_file["related_resources_text"],
                "transcript": json_file["transcript"],
                "embedded_media": [],
            }
            # Find all children of linked embedded media
            for child in jsons:
                if child["parent_uid"] == json_file["_uid"]:
                    embedded_media = {
                        "uid": child["_uid"],
                        "parent_uid": child["parent_uid"],
                        "id": child["id"],
                        "title": child["title"],
                        "type": child.get("media_asset_type"),
                    }
                    if "media_location" in child and child["media_location"]:
                        embedded_media["media_location"] = child["media_location"]
                    if "technical_location" in child and child["technical_location"]:
                        embedded_media["technical_location"] = child[
                            "technical_location"
                        ]
                    temp["embedded_media"].append(embedded_media)
            linked_media_parents[json_file["inline_embed_id"]] = temp
    return linked_media_parents


def compose_course_features(jsons, course_pages):
    """
    Create course feature dicts from input JSONs

    Args:
        jsons (list of dict): Course info
        course_pages (list of dict): Course page info generated from compose_pages

    Returns:
        list of dict:
            Course feature info
    """
    course_features = []
    feature_requirements = jsons[0].get("feature_requirements")
    if feature_requirements:
        for feature_requirement in feature_requirements:
            page = course_page_from_relative_url(
                feature_requirement["ocw_feature_url"], course_pages
            )
            if page:
                course_feature = copy.copy(feature_requirement)
                course_feature["ocw_feature_url"] = "./resolveuid/" + page["uid"]
                course_features.append(course_feature)
    return course_features


def compose_course_feature_tags(jsons, course_pages):
    """
    Create course feature tag dicts from input JSONs

    Args:
        jsons (list of dict): Course info
        course_pages (list of dict): Course page info generated from compose_pages

    Returns:
        list of dict:
            Course feature info
    """
    course_feature_tags = []
    feature_requirements = jsons[0].get("feature_requirements")
    if feature_requirements:
        for feature_requirement in feature_requirements:
            page = course_page_from_relative_url(
                feature_requirement["ocw_feature_url"], course_pages
            )
            if page:
                matching_tag = match_course_feature_tag(
                    feature_requirement["ocw_feature"],
                    feature_requirement["ocw_subfeature"],
                )
                if matching_tag:
                    course_feature_tags.append(
                        {
                            "course_feature_tag": matching_tag,
                            "ocw_feature_url": "./resolveuid/" + page["uid"],
                        }
                    )
    return course_feature_tags


def gather_foreign_media(jsons):
    """
    Information about links to foreign media

    Args:
        jsons (list of dict): Course input

    Returns:
        list of dict: Information about each link to foreign media
    """
    containing_keys = [
        "bottomtext",
        "courseoutcomestext",
        "description",
        "image_caption_text",
        "optional_text",
        "text",
    ]
    large_media_links = []
    for course_json in jsons:  # pylint: disable=too-many-nested-blocks
        for key in containing_keys:
            if (
                key in course_json
                and isinstance(course_json[key], str)
                and "/ans7870/" in course_json[key]
            ):
                parser = CustomHTMLParser()
                parser.feed(course_json[key])
                if parser.output_list:
                    for link in parser.output_list:
                        if link and "/ans7870/" in link and "." in link.split("/")[-1]:
                            obj = {
                                "parent_uid": course_json.get("_uid"),
                                "link": link.strip(),
                            }
                            large_media_links.append(obj)
    return large_media_links


def compose_open_learning_library_related(jsons):
    """
    Compile list of related courses

    Args:
        jsons (list of dict): Course input

    Returns:
        list of dict:
            Info about related courses
    """
    open_learning_library_related = []
    courselist_features = jsons[0].get("courselist_features")
    if courselist_features:
        for courselist_feature in courselist_features:
            if courselist_feature["ocw_feature"] == "Open Learning Library":
                raw_url = courselist_feature["ocw_feature_url"]
                courses_and_links = raw_url.split(",")
                for course_and_link in courses_and_links:
                    related_course = {}
                    try:
                        course, url = course_and_link.strip().split("::")
                        related_course["course"] = course
                        related_course["url"] = url
                        open_learning_library_related.append(related_course)
                    except:  # pylint: disable=bare-except
                        log.exception(
                            "Unable to parse ocw_feature_url %s for course %s",
                            raw_url,
                            jsons[0].get("short_url"),
                        )
    return open_learning_library_related


class OCWParser:  # pylint: disable=too-many-instance-attributes
    """
    Parses JSON files from OCW's Plone database and outputs combined JSON files
    with S3 links for media
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        course_dir=None,
        destination_dir=None,
        static_prefix="",
        loaded_jsons=None,
        upload_to_s3=False,
        s3_bucket_name="",
        s3_bucket_access_key="",
        s3_bucket_secret_access_key="",
        s3_target_folder="",
        beautify_parsed_json=False,
        create_vtt_files=False,
    ):
        if not (course_dir and destination_dir) and not loaded_jsons:
            raise Exception(
                "OCWParser must be initiated with course_dir and destination_dir or loaded_jsons"
            )

        if loaded_jsons is None:
            loaded_jsons = []

        self.course_dir = Path(course_dir) if course_dir else course_dir
        self.destination_dir = (
            Path(destination_dir) if destination_dir else destination_dir
        )
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
        if create_vtt_files:
            self.populate_vtt_files()
        if self.jsons:
            self.parsed_json = self.generate_parsed_json()
            if self.destination_dir:
                self.destination_dir = self.destination_dir / self.jsons[0].get("id")
        self.beautify_parsed_json = beautify_parsed_json

    def get_parsed_json(self):
        """
        Return parsed JSON

        Returns:
            dict: The combined JSON
        """
        return self.parsed_json

    def setup_s3_uploading(
        self,
        s3_bucket_name,
        s3_bucket_access_key,
        s3_bucket_secret_access_key,
        folder="",
    ):
        """
        Configure S3 uploading

        Args:
            s3_bucket_name (str): Bucket name
            s3_bucket_access_key (str): S3 access key
            s3_bucket_secret_access_key (str): S3 secret
            folder (str): Target folder
        """
        self.upload_to_s3 = True
        self.s3_bucket_name = s3_bucket_name
        self.s3_bucket_access_key = s3_bucket_access_key
        self.s3_bucket_secret_access_key = s3_bucket_secret_access_key
        self.s3_target_folder = folder

    def generate_parsed_json(self):
        """
        Generates parsed JSON file for the course

        Returns:
            dict: The combined JSON for the course
        """
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
        aka_course_numbers = self.jsons[0].get("aka_course_number")
        technical_location = self.jsons[0].get("technical_location")
        instructors = self.jsons[0].get("instructors")
        course_pages = compose_pages(self.jsons)
        course_files, self.media_jsons = compose_media(
            self.jsons, self.get_s3_base_url()
        )
        foreign_media = gather_foreign_media(self.jsons)
        self.large_media_links = foreign_media

        # Generate parsed JSON
        new_json = {
            "uid": self.jsons[0].get("_uid"),
            "title": self.jsons[0].get("title"),
            "description": self.jsons[1].get("description"),
            "other_information_text": self.jsons[1].get("other_information_text"),
            "first_published_to_production": _get(
                self.jsons[0], "first_published_to_production"
            ),
            "last_published_to_production": _get(
                self.jsons[0], "last_published_to_production"
            ),
            "last_unpublishing_date": _get(self.jsons[0], "last_unpublishing_date"),
            "retirement_date": _get(self.jsons[0], "retirement_date"),
            "sort_as": self.jsons[0].get("sort_as"),
            "department_number": master_course.split(".")[0] if master_course else "",
            "master_course_number": master_course.split(".")[1]
            if master_course
            else "",
            "new_course_numbers": [
                {
                    key.replace("aka_", "") if key.startswith("aka_") else key: value
                    for key, value in aka_course_number.items()
                }
                for aka_course_number in aka_course_numbers
            ]
            if aka_course_numbers
            else [],
            "other_version_parent_uids": self.jsons[0].get("master_subject"),
            "from_semester": self.jsons[0].get("from_semester"),
            "from_year": self.jsons[0].get("from_year"),
            "to_semester": self.jsons[0].get("to_semester"),
            "to_year": self.jsons[0].get("to_year"),
            "course_level": self.jsons[0].get("course_level"),
            "url": technical_location.split("ocw.mit.edu")[1]
            if technical_location
            else "",
            "short_url": self.jsons[0].get("id"),
            "image_src": self.course_image_s3_link,
            "thumbnail_image_src": self.course_thumbnail_image_s3_link,
            "image_description": self.course_image_alt_text,
            "thumbnail_image_description": self.course_thumbnail_image_alt_text,
            "image_alternate_text": self.jsons[1].get("image_alternate_text"),
            "image_caption_text": self.jsons[1].get("image_caption_text"),
            "tags": [{"name": tag} for tag in self.jsons[0].get("subject")],
            "instructors": [
                {key: value for key, value in instructor.items() if key != "mit_id"}
                for instructor in instructors
            ]
            if instructors
            else [],
            "language": self.jsons[0].get("language"),
            "extra_course_number": self.jsons[0].get("linked_course_number"),
            "course_collections": self.jsons[0].get("category_features"),
            "course_pages": course_pages,
            "course_features": compose_course_features(self.jsons, course_pages),
            "course_feature_tags": compose_course_feature_tags(
                self.jsons, course_pages
            ),
            "course_files": course_files,
            "course_embedded_media": compose_embedded_media(self.jsons),
            "course_foreign_files": foreign_media,
            "open_learning_library_related": compose_open_learning_library_related(
                self.jsons
            ),
            "dspace_handle": self.jsons[0].get("dspace_handle"),
            "features_tracking": self.jsons[0].get("features_tracking"),
            "is_update_of": self.jsons[0].get("is_update_of"),
        }

        self.parsed_json = new_json
        return new_json

    def extract_media_locally(self):
        """
        Output media files to a local path
        """
        if not self.media_jsons:
            log.debug("You have to compose media for course first!")
            return

        path_to_containing_folder = (
            self.destination_dir / "output" / self.static_prefix
            if self.static_prefix
            else self.destination_dir / "output" / "static_files"
        )
        url_path_to_media = (
            self.static_prefix if self.static_prefix else str(path_to_containing_folder)
        )
        os.makedirs(path_to_containing_folder, exist_ok=True)
        for page in compose_pages(self.jsons):
            filename, html = htmlify(page)
            if filename and html:
                with open(path_to_containing_folder / filename, "w") as file:
                    file.write(html)
        for media_json in self.media_jsons:
            uid = media_json.get("_uid")
            file_name = uid + "_" + media_json.get("id")
            binary_data = get_binary_data(media_json)
            if binary_data is not None:
                with open(path_to_containing_folder / file_name, "wb") as file:
                    file.write(binary_data)
                update_file_location(
                    self.parsed_json,
                    urljoin(url_path_to_media, file_name),
                    uid,
                )
                log.info("Extracted %s", file_name)
            else:
                json_file = media_json["actual_file_name"]
                log.error(
                    "Media file %s without either datafield key and no working link "
                    "to be fetched for course %s and UID %s",
                    json_file,
                    self.parsed_json.get("short_url"),
                    uid,
                )
        log.info("Done! extracted static media to %s", path_to_containing_folder)
        self.export_parsed_json()

    def extract_foreign_media_locally(self):
        """
        Extract foreign media files to a local directory
        """
        if not self.large_media_links:
            log.debug("Your course has 0 foreign media files")
            return

        path_to_containing_folder = (
            self.destination_dir / "output" / self.static_prefix
            if self.static_prefix
            else self.destination_dir / "output" / "static_files"
        )
        url_path_to_media = (
            self.static_prefix if self.static_prefix else str(path_to_containing_folder)
        )
        os.makedirs(path_to_containing_folder, exist_ok=True)
        for media in self.large_media_links:
            file_name = media["link"].split("/")[-1]
            response = requests.get(media["link"])
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                log.exception(
                    "Could not fetch link %s for course %s",
                    media["link"],
                    self.parsed_json.get("short_url"),
                )
                continue
            with open(path_to_containing_folder / file_name, "wb") as file:
                file.write(response.content)
            update_file_location(self.parsed_json, url_path_to_media + file_name)
            log.info("Extracted %s", file_name)
        log.info("Done! extracted foreign media to %s", path_to_containing_folder)
        self.export_parsed_json()

    def export_parsed_json(self, s3_links=False, upload_parsed_json=False):
        """
        Export parsed JSON to a file

        Args:
            s3_links (bool): Also upload media files to S3
            upload_parsed_json (bool): And upload the parsed JSON file as well
        """
        if s3_links:
            self.upload_all_media_to_s3(upload_parsed_json=upload_parsed_json)
        os.makedirs(self.destination_dir, exist_ok=True)
        file_path = self.destination_dir / "{}_parsed.json".format(
            self.parsed_json["short_url"]
        )
        with open(file_path, "w") as json_file:
            if self.beautify_parsed_json:
                json.dump(self.parsed_json, json_file, sort_keys=True, indent=4)
            else:
                json.dump(self.parsed_json, json_file)
        log.info("Extracted %s", file_path)

    def find_course_image_s3_link(self):
        """
        Find the course image and use it to set the thumbnail in the parsed JSON
        """
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

                if (
                    self.course_thumbnail_image_uid
                    and uid == self.course_thumbnail_image_uid
                ):
                    self.course_thumbnail_image_s3_link = bucket_base_url + filename
                    self.course_thumbnail_image_alt_text = file.get("description")
                    self.parsed_json[
                        "thumbnail_image_src"
                    ] = self.course_thumbnail_image_s3_link
                    self.parsed_json[
                        "thumbnail_image_description"
                    ] = self.course_thumbnail_image_alt_text

    def get_s3_base_url(self):  # pylint: disable=inconsistent-return-statements
        """
        Get the S3 URL with target folder included if it's set

        Returns:
            str: The S3 bucket URL
        """
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
        """
        Update the thumbnail image and return the S3 bucket

        Returns:
            s3.Bucket: A boto3 S3 bucket
        """
        self.find_course_image_s3_link()
        return boto3.resource(
            "s3",
            aws_access_key_id=self.s3_bucket_access_key,
            aws_secret_access_key=self.s3_bucket_secret_access_key,
        ).Bucket(self.s3_bucket_name)

    def update_s3_content(  # pylint: disable=too-many-arguments, too-many-locals, too-many-branches, too-many-statements
        self,
        upload=None,
        update_pages=True,
        update_media=True,
        media_uid_filter=None,
        update_external_media=True,
        chunk_size=1000000,
    ):
        """
        Update file_location for parsed JSON content and optionally upload to S3

        Args:
            upload (bool): If true, also upload media files to S3 after updating file_location
            update_pages (bool): If true, update content relating to course pages
            update_media (bool): If true, update content relating to media files
            media_uid_filter (???):
            update_external_media (bool): If true, update foreign media file content
            chunk_size (int): Chunk size to use when uploading to S3
        """
        upload_to_s3 = self.upload_to_s3
        if upload:
            upload_to_s3 = upload
        bucket_base_url = self.get_s3_base_url()
        if bucket_base_url:
            s3_bucket = self.get_s3_bucket()
            if update_pages:
                for page in compose_pages(self.jsons):
                    filename, html = htmlify(page)
                    if filename and html:
                        if upload_to_s3:
                            s3_bucket.put_object(
                                Key=self.s3_target_folder + filename,
                                Body=html,
                                ACL="public-read",
                            )
                        update_file_location(
                            self.parsed_json,
                            bucket_base_url + filename,
                            page.get("uid"),
                        )
            if update_media:
                if media_uid_filter:
                    media_jsons = [
                        media_json
                        for media_json in self.media_jsons
                        if media_json.get("_uid") in media_uid_filter
                    ]
                else:
                    media_jsons = self.media_jsons
                for file in media_jsons:
                    uid = file.get("_uid")
                    filename = uid + "_" + file.get("id")
                    binary_data = get_binary_data(file)
                    if binary_data is None:
                        log.error(
                            "Could not load binary data for file %s in json file %s for course %s",
                            filename,
                            file.get("actual_file_name"),
                            self.parsed_json.get("short_url"),
                        )
                        continue
                    if upload_to_s3:
                        s3_bucket.put_object(
                            Key=self.s3_target_folder + filename,
                            Body=binary_data,
                            ACL="public-read",
                        )
                    update_file_location(
                        self.parsed_json, bucket_base_url + filename, uid
                    )
                    if self.course_image_uid and uid == self.course_image_uid:
                        self.course_image_s3_link = bucket_base_url + filename
                        self.course_image_alt_text = file.get("description")
                        self.parsed_json["image_src"] = self.course_image_s3_link
                        self.parsed_json[
                            "image_description"
                        ] = self.course_image_alt_text

                    if (
                        self.course_thumbnail_image_uid
                        and uid == self.course_thumbnail_image_uid
                    ):
                        self.course_thumbnail_image_s3_link = bucket_base_url + filename
                        self.course_thumbnail_image_alt_text = file.get("description")
                        self.parsed_json[
                            "thumbnail_image_src"
                        ] = self.course_thumbnail_image_s3_link
                        self.parsed_json[
                            "thumbnail_image_description"
                        ] = self.course_thumbnail_image_alt_text
            if update_external_media:
                for media in self.large_media_links:
                    filename = media["link"].split("/")[-1]

                    if upload_to_s3:
                        try:
                            response = requests.get(media["link"], stream=True)
                            response.raise_for_status()
                            s3_uri = (
                                f"s3://{self.s3_bucket_access_key}:{self.s3_bucket_secret_access_key}@"
                                f"{self.s3_bucket_name}/"
                            )
                            with smart_open(
                                s3_uri + self.s3_target_folder + filename, "wb"
                            ) as handle:
                                for chunk in response.iter_content(
                                    chunk_size=chunk_size
                                ):
                                    handle.write(chunk)
                            response.close()
                            log.info("Uploaded %s", filename)
                        except requests.exceptions.HTTPError:
                            log.exception(
                                "Could NOT upload %s for course %s from link %s",
                                filename,
                                self.parsed_json.get("short_url"),
                                media["link"],
                            )
                    update_file_location(self.parsed_json, bucket_base_url + filename)

    def upload_all_media_to_s3(self, upload_parsed_json=False):
        """
        Update content and upload to S3

        Args:
            upload_parsed_json (bool): If True, upload parsed JSON to S3
        """
        self.update_s3_content()
        if upload_parsed_json:
            s3_bucket = self.get_s3_bucket()
            self.upload_parsed_json_to_s3(s3_bucket)

    def upload_parsed_json_to_s3(self, s3_bucket):
        """
        Upload parsed JSON to S3

        Args:
            s3_bucket (s3.Bucket): An S3 bucket
        """
        short_url = self.parsed_json.get("short_url")
        if short_url:
            s3_bucket.put_object(
                Key=self.s3_target_folder + f"{short_url}_parsed.json",
                Body=json.dumps(self.parsed_json),
                ACL="private",
            )
        else:
            raise Exception("No short_url found in parsed_json")

    def upload_course_image(self):
        """
        Upload course image and parsed JSON to S3
        """
        s3_bucket = self.get_s3_bucket()
        self.update_s3_content(upload=False)
        for file in self.media_jsons:
            uid = file.get("_uid")
            if uid in (self.course_image_uid, self.course_thumbnail_image_uid):
                self.update_s3_content(
                    update_pages=False,
                    update_external_media=False,
                    media_uid_filter=[uid],
                )
        self.upload_parsed_json_to_s3(s3_bucket)

    def populate_vtt_files(self):
        """
        for each srt caption file create a vtt file
        """
        for loaded_json in self.jsons:
            if loaded_json["_content_type"] == "application/x-subrip":
                new_json = convert_to_vtt(loaded_json)
                if new_json:
                    self.jsons.append(new_json)
