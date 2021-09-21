"""Utility functions for ocw-data-parser"""
import re
import tempfile
from base64 import b64decode, b64encode
from pathlib import Path
from datetime import datetime
import uuid

import os
import shutil
import json
import logging
import requests
import webvtt

import pytz

log = logging.getLogger(__name__)


def course_page_from_relative_url(url, course_pages):
    """
    Return a course_page object that matches a course page based on a relative url

    Args:
        url (string): A relative URL to match against a course_page
        course_pages: An array of parsed course pages from a course
    """
    if url:
        for page in course_pages:
            ocw_feature_url_parts = url.split("/")
            ocw_feature_short_url = url
            if len(ocw_feature_url_parts) > 1:
                ocw_feature_short_url = (
                    ocw_feature_url_parts[-2] + "/" + ocw_feature_url_parts[-1]
                )
            if (
                page["short_url"] in ocw_feature_short_url
                and "index.htm" not in page["short_url"]
            ):
                return page
    return None


def update_file_location(parsed_json, new_file_location, obj_uid=""):
    """
    Update file_location for an object.

    If obj_uid is set, the function will look in course_pages and course_files for the content to update.
    Otherwise, the function will look in course_foreign_files and see if the filename matches new_file_location.

    Args:
        parsed_json (dict): The parsed JSON output to be modified with the updated file_location
        new_file_location (str): The new file_location to be set on the object
        obj_uid (str): UID of the file to be updated
    """
    if obj_uid:
        for page in parsed_json["course_pages"]:
            if page["uid"] == obj_uid:
                page["file_location"] = new_file_location
        for course_file in parsed_json["course_files"]:
            if course_file["uid"] == obj_uid:
                course_file["file_location"] = new_file_location
    else:
        for media in parsed_json["course_foreign_files"]:
            original_filename = media["link"].split("/")[-1]
            passed_filename = new_file_location.split("/")[-1]
            if original_filename == passed_filename:
                media["file_location"] = new_file_location


def get_binary_data(json_obj):
    """
    Look in _datafield_image or _datafield_file for base64 encoded binary data. If it's not present,
    try to download it.

    Args:
        json_obj (dict): JSON from one of the input course files

    Returns:
        bytes or None: Binary data for a file, or None if it couldn't be found
    """
    key = ""
    if "_datafield_image" in json_obj:
        key = "_datafield_image"
    elif "_datafield_file" in json_obj:
        key = "_datafield_file"
    if key:
        b64_data = json_obj[key]["data"]
        return b64decode(b64_data)

    url = None
    if "unique_identifier" in json_obj:
        url = json_obj["unique_identifier"]
    elif "technical_location" in json_obj:
        url = json_obj["technical_location"]

    if url:
        resp = requests.get(url)
        if resp.ok:
            return resp.content
    return None


def print_error(message):
    """Print an error"""
    print("\x1b[0;31;40m Error:\x1b[0m " + message)


def print_success(message):
    """Print success message"""
    print("\x1b[0;32;40m Success:\x1b[0m " + message)


def find_all_values_for_key(jsons, key="_content_type"):
    """
    Find all _content_type instances in each JSON which aren't text/plain or text/html.

    Args:
        jsons (list of dict): The input course JSON dicts
        key (str): An alternative place to look for the content type

    Returns:
        list of str: A list of content types
    """
    excluded_values = ["text/plain", "text/html"]
    result = set()
    for j in jsons:
        if key in j and j[key]:
            result.add(j[key])

    # Remove excluded values
    for value in excluded_values:
        if value in result:
            result.remove(value)
    return result


def htmlify(page):
    """
    Wrap contents of a page dict in basic HTML

    Args:
        page (dict): A course page dict

    Returns:
        tuple[str, str]: A new filename and the HTML, or None, None if the text is empty
    """
    safe_text = page.get("text")
    if safe_text:
        file_name = page.get("uid") + "_" + page.get("short_url") + ".html"
        html = "<html><head></head><body>" + safe_text + "</body></html>"
        return file_name, html
    return None, None


def parse_date(date_str):
    """
    Parse date string in a format like 2016/02/02 20:28:06 US/Eastern

    Args:
        date_str (str): Datetime object as string in the following format (2016/02/02 20:28:06 US/Eastern)
    Returns:
        datetime: Datetime object if passed date is valid, otherwise None
    """
    if date_str and date_str != "None":
        date_pieces = date_str.split(" ")  # e.g. 2016/02/02 20:28:06 US/Eastern
        date_pieces[0] = date_pieces[0].replace("/", "-")
        # Discard milliseconds if exists
        date_pieces[1] = (
            date_pieces[1][:-4] if "." in date_pieces[1] else date_pieces[1]
        )
        timezone_piece = date_pieces.pop(2)
        timezone = (
            pytz.timezone(timezone_piece)
            if "GMT" not in timezone_piece
            else pytz.timezone("Etc/" + timezone_piece)
        )
        tz_stripped_date = datetime.strptime(" ".join(date_pieces), "%Y-%m-%d %H:%M:%S")
        tz_aware_date = timezone.localize(tz_stripped_date)
        tz_aware_date = tz_aware_date.astimezone(pytz.utc)
        return tz_aware_date
    return None


def is_course_published(source_path):
    """
    Determine if the course is published or not.

    Args:
        source_path(str or Path): The path to the raw course JSON

    Returns:
        boolean: True if published, False if not
    """
    source_path = Path(source_path) if source_path else None

    # Collect last modified timestamps for all course files of the course
    is_published = True
    matches = list(source_path.rglob("1.json"))
    if not matches:
        raise Exception(f"Could not find 1.json for {source_path}")

    with open(matches[0], "r") as infile:
        first_json = json.load(infile)

    last_published_to_production = parse_date(
        first_json.get("last_published_to_production", None)
    )
    last_unpublishing_date = parse_date(first_json.get("last_unpublishing_date", None))
    if last_published_to_production is None or (
        last_unpublishing_date
        and (last_unpublishing_date > last_published_to_production)
    ):
        is_published = False

    return is_published


def parse_all(  # pylint: disable=too-many-arguments, too-many-locals
    courses_dir,
    destination_dir,
    upload_parsed_json,
    s3_bucket="",
    s3_links=False,
    overwrite=False,
    beautify_parsed_json=False,
    courses_json_path=None,
    create_vtt_files=False,
):
    """
    Convert multiple courses in a directory to the parsed JSON format in destination_dir

    Args:
        courses_dir (str or Path or None): The directory containing JSON from Plone for each course
        destination_dir (str or Path or None): The directory to write courses to with the parsed JSON
        upload_parsed_json (bool): Upload the parsed JSON to S3
        s3_bucket (str): The S3 bucket to upload to
        s3_links (bool): If true, upload media files as well
        overwrite (bool): If true, erase the destination directory for each course first
        beautify_parsed_json (bool): Pretty print JSON files which are created
        courses_json_path (str or Path or None): If set, only convert courses listed in this file
        create_vtt_files (bool): If true, convert all srt caption files to vtt
    """
    import ocw_data_parser.ocw_data_parser  # pylint: disable=import-outside-toplevel

    courses_dir = Path(courses_dir) if courses_dir else None
    destination_dir = Path(destination_dir) if destination_dir else None

    course_list = None
    if courses_json_path is not None:
        with open(courses_json_path) as file:
            course_list = json.load(file)["courses"]

    for first_json_path in courses_dir.rglob("1.json"):
        source_path = first_json_path.parent.parent
        course_dir = source_path.name

        if course_list is not None and course_dir not in course_list:
            continue

        dest_path = destination_dir / course_dir
        if dest_path.exists() and overwrite:
            shutil.rmtree(dest_path)
        if not dest_path.exists():
            os.makedirs(dest_path)
            parser = ocw_data_parser.OCWParser(
                course_dir=source_path,
                destination_dir=destination_dir,
                s3_bucket_name=s3_bucket,
                s3_target_folder=course_dir,
                beautify_parsed_json=beautify_parsed_json,
                create_vtt_files=create_vtt_files,
            )
            perform_upload = (
                s3_links and upload_parsed_json and is_course_published(source_path)
            )
            if perform_upload:
                parser.setup_s3_uploading(
                    s3_bucket,
                    os.environ["AWS_ACCESS_KEY_ID"],
                    os.environ["AWS_SECRET_ACCESS_KEY"],
                    course_dir,
                )
                # just upload parsed json, and update media links.
                parser.upload_to_s3 = False
            parser.export_parsed_json(
                s3_links=s3_links, upload_parsed_json=perform_upload
            )


def convert_to_vtt(loaded_json):
    """
    Convert a json file with srt captions data to vtt format

    Args:
        loaded_json (dict): The content of JSON file

    Returns:
        dict: copy of the json file with the _datafield_file converted to vtt format
    """
    if loaded_json["id"].endswith(".vtt"):
        return None
    new_json = dict(loaded_json)

    new_json["id"] = update_srt_to_vtt(loaded_json["id"])
    new_json["technical_location"] = update_srt_to_vtt(
        loaded_json["technical_location"]
    )
    new_json["_uid"] = uuid.uuid5(uuid.UUID(loaded_json["_uid"]), "vtt").hex
    binary_data = get_binary_data(loaded_json)
    if binary_data is not None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(Path(temp_dir) / "data", "wb") as file:
                file.write(binary_data)
                file.flush()
                try:
                    webvtt.from_srt(Path(temp_dir) / "data").save()
                except webvtt.errors.MalformedFileError as msg:
                    log.exception(
                        "This file is malformed and cannot be converted to vtt %s. %s",
                        loaded_json["id"],
                        msg,
                    )
                    return None
                except:  # pylint: disable=bare-except
                    log.exception(
                        "Unknown error when converting vtt %s", loaded_json["id"]
                    )
                    return None
            with open(Path(temp_dir) / "data.vtt", "rb") as file:
                data = file.read()
            new_json["_datafield_file"] = {
                "encoding": "base64",
                "data": b64encode(data).decode(),
            }
            return new_json
    return None


def update_srt_to_vtt(field):
    """Find the extension in the field and updates it to .vtt"""
    return re.sub(r".srt$", ".vtt", field)
