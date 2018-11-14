import base64
import os

from utils import (get_correct_path, is_json, load_json_file, EXCLUDED_TYPES, ALL_ACCEPTED_MEDIA_TYPES,
    missing_binary_data_media_jsons, find_all_possible_vals_for_key, get_media_dict)


def extract_media_files(base_dir, destination_dir):
    """
    Extract media files from jsons within base_dir
    base_dir: directory of course
    destination_dir: where extract media files will live
    """
    base_dir = get_correct_path(base_dir)
    destination_dir = get_correct_path(destination_dir)
    
    for item in os.listdir(base_dir):
        item = base_dir + item
        if os.path.isdir(item):
            extract_media_files(item, destination_dir)
        elif is_json(item):
            loaded_json = load_json_file(item)
            if not loaded_json:  # some json's are corrupted
                continue
            extract_media_file(loaded_json, destination_dir)


def extract_media_files_from_list(jsons, destination_dir):
    destination_dir = get_correct_path(destination_dir) + 'static_files/'
    os.makedirs(destination_dir, exist_ok=True)
    for k, j in jsons.items():
        extract_media_file(j, destination_dir)


def extract_media_file(jsonfile, destination_dir):
    key = ""
    filename = jsonfile["id"]
    if "_datafield_image" in jsonfile:
        key = "_datafield_image"
    elif "_datafield_file" in jsonfile:
        key = "_datafield_file"
    if key:
        with open(destination_dir + filename, "wb") as f:
            data = base64.b64decode(jsonfile[key]["data"])
            f.write(data)
    else:
        print(f"Media file '{jsonfile}' without either datafield key")


def find_media_jsons_with_missing_binary(base_dir):
    """
    Add json files path with missing binary data to the global dict (missing_binary_data_media_jsons)
    base_dir: directory of course

    Note: result of running this function will be saved to missing_binary_data_media_jsons dictionary
          and can be accessed as follows: json_parser.missing_binary_data_media_jsons
    """
    base_dir = get_correct_path(base_dir)
    for item in os.listdir(base_dir):
        item = base_dir + item
        if os.path.isdir(item):
            find_media_jsons_with_missing_binary(item)
        elif is_json(item):
            loaded_json = load_json_file(item)
            content_type = loaded_json["_content_type"]
            if loaded_json and \
                    content_type not in EXCLUDED_TYPES and \
                    content_type in ALL_ACCEPTED_MEDIA_TYPES and \
                    "_datafield_image" not in loaded_json and \
                    "_datafield_file" not in loaded_json:
                missing_binary_data_media_jsons[content_type].append(item)


def compose_and_extract_media(jsons, path_of_course, destination):
    all_types = find_all_possible_vals_for_key(path_of_course, "_content_type")
    media_types_in_course = [x for x in all_types if x not in ["text/plain", "text/html"]]
    media_jsons = {}
    media = []

    # Get the jsons that contain media files
    for idx, j in enumerate(jsons):
        if j["_content_type"] in media_types_in_course:
            media_jsons[str(idx + 1)] = j

    # Extract all media files inside a subdirectory
    extract_media_files_from_list(media_jsons, destination)

    # Compose list of jsons for the extracted media
    for idx, j in media_jsons.items():
        media.append(get_media_dict(j, idx, path_of_course))
    return media