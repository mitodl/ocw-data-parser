import json
import logging


log = logging.getLogger(__name__)


def update_file_location(master_json, new_file_location, obj_uid=""):
    if obj_uid:
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
        except json.JSONDecodeError:
            log.exception("Failed to load %s", path)


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
