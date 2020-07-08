import os
import shutil
import json
import logging
import ocw_data_parser.ocw_data_parser

log = logging.getLogger(__name__)


def update_file_location(master_json, new_file_location, obj_uid=""):
    if obj_uid:
        for p in master_json["course_pages"]:
            if p["uid"] == obj_uid:
                p["file_location"] = new_file_location
        for j in master_json["course_files"]:
            if j["uid"] == obj_uid:
                j["file_location"] = new_file_location
    else:
        for media in master_json["course_foreign_files"]:
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


def is_json(path_to_file):
    return path_to_file.split("/")[-1].split(".")[1] == "json"


def get_correct_path(directory):
    if not directory:
        return ""
    return directory if directory[-1] == "/" else directory + "/"

def load_json_file(path):
    with open(path, 'r') as f:
        try:
            loaded_json = json.load(f)
            return loaded_json
        except json.JSONDecodeError as err:
            log.exception("Failed to load %s", path)
            raise err


def print_error(message):
    print("\x1b[0;31;40m Error:\x1b[0m " + message)


def print_success(message):
    print("\x1b[0;32;40m Success:\x1b[0m " + message)


def safe_get(j, key, print_error_message=False):
    value = j.get(key)
    if value or isinstance(value, list):
        return value
    elif print_error_message:
        log.error("%s: Value for %s is NOT found", (j["actual_file_name"], key))


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
    safe_text = safe_get(page, "text")
    if safe_text:
        file_name = safe_get(page, "uid") + "_" + safe_get(page, "short_url") + ".html"
        html = "<html><head></head><body>" + safe_text + "</body></html>"
        return file_name, html
    return None, None

def parse_all(courses_dir, destination_dir, s3_bucket="", s3_links=False, overwrite=False, beautify_master_json=False):
    for course_dir in os.listdir(courses_dir):
        source_path = "{}/".format(os.path.join(courses_dir, course_dir))
        dest_path = os.path.join(destination_dir, course_dir)
        if os.path.isdir(source_path):
            if os.path.exists(dest_path) and overwrite:
                shutil.rmtree(dest_path)
            if not os.path.exists(dest_path):
                os.makedirs(dest_path)
                parser = ocw_data_parser.OCWParser(course_dir=source_path, destination_dir=destination_dir, s3_bucket_name=s3_bucket,
                                s3_target_folder=course_dir, beautify_master_json=beautify_master_json)
                parser.export_master_json(s3_links=s3_links)
                master_path = os.path.join(dest_path, "master")
                if os.path.isdir(master_path):
                    for filename in os.listdir(master_path):
                        shutil.move(os.path.join(master_path, filename),
                                    os.path.join(dest_path, filename))
                    shutil.rmtree(master_path)
