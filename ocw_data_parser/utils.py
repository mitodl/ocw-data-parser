import os
import shutil
import json
import logging
from pathlib import Path
from datetime import datetime

import pytz

import ocw_data_parser.ocw_data_parser

log = logging.getLogger(__name__)


def update_file_location(parsed_json, new_file_location, obj_uid=""):
    if obj_uid:
        for p in parsed_json["course_pages"]:
            if p["uid"] == obj_uid:
                p["file_location"] = new_file_location
        for j in parsed_json["course_files"]:
            if j["uid"] == obj_uid:
                j["file_location"] = new_file_location
    else:
        for media in parsed_json["course_foreign_files"]:
            original_filename = media["link"].split("/")[-1]
            passed_filename = new_file_location.split("/")[-1]
            if original_filename == passed_filename:
                media["file_location"] = new_file_location


def get_binary_data(json_obj):
    key = ""
    if "_datafield_image" in json_obj:
        key = "_datafield_image"
    elif "_datafield_file" in json_obj:
        key = "_datafield_file"
    if key:
        return json_obj[key]["data"]
    return None


def print_error(message):
    print("\x1b[0;31;40m Error:\x1b[0m " + message)


def print_success(message):
    print("\x1b[0;32;40m Success:\x1b[0m " + message)


def find_all_values_for_key(jsons, key="_content_type"):
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
        date_str (String): Datetime object as string in the following format (2016/02/02 20:28:06 US/Eastern)
    Returns:
        Datetime object if passed date is valid, otherwise None
    """
    if date_str and date_str != "None":
        date_pieces = date_str.split(" ")  # e.g. 2016/02/02 20:28:06 US/Eastern
        date_pieces[0] = date_pieces[0].replace("/", "-")
        # Discard milliseconds if exists
        date_pieces[1] = (
            date_pieces[1][:-4] if "." in date_pieces[1] else date_pieces[1]
        )
        tz = date_pieces.pop(2)
        timezone = pytz.timezone(tz) if "GMT" not in tz else pytz.timezone("Etc/" + tz)
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
    last_unpublishing_date = parse_date(
        first_json.get("last_unpublishing_date", None)
    )
    if last_published_to_production is None or (
        last_unpublishing_date
        and (last_unpublishing_date > last_published_to_production)
    ):
        is_published = False

    return is_published


def parse_all(
    courses_dir,
    destination_dir,
    upload_parsed_json,
    s3_bucket="",
    s3_links=False,
    overwrite=False,
    beautify_parsed_json=False,
    courses_json_path=None
):
    source_path = Path(courses_dir) if courses_dir else None
    destination_dir = Path(destination_dir) if destination_dir else None

    course_list = None
    if courses_json_path is not None:
        with open(courses_json_path) as f:
            course_list = json.load(f)['courses']

    for first_json_path in source_path.rglob("1.json"):
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
