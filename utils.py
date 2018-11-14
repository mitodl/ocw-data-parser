import copy
import json
import os
from collections import OrderedDict


def compose_pages(jsons, path_of_course):
    # note: JSON pages are recognized by their _content_type value of text/html
    pages = []
    loaded_pages = {}
    # Find all the pages within a directory
    for idx, j in enumerate(jsons):
        if j["_content_type"] == "text/html":
            loaded_pages[str(idx + 1)] = j
    for key, page in loaded_pages.items():
        pages.append(get_course_sub_page_dict(page, key, path_of_course))

    return pages


def compose_citation(jsons):
    instructors = ""
    # if more than one instructor
    if len(jsons[0]["instructors"]) > 1:
        for instructor in jsons[0]["instructors"][:-1]:
            first_name = instructor["first_name"]
            last_name = instructor["last_name"]
            instructors += f"{first_name} {last_name}, "
        else:
            first_name = jsons[0]["instructors"][-1]["first_name"]
            last_name = jsons[0]["instructors"][-1]["last_name"]
            instructors += f"and {first_name} {last_name}"
    else:
        # if only one instructor
        first_name = jsons[0]["instructors"][0]["first_name"]
        last_name = jsons[0]["instructors"][0]["last_name"]
        instructors = f"{first_name} {last_name}"
    course_number = jsons[0]["master_course_number"]
    course_title = jsons[0]["title"]
    from_semester = jsons[0]["from_semester"]
    from_year = jsons[0]["from_year"]
    course_license = jsons[0]["license"]
    citation = f"<p>{instructors}. {course_number} {course_title}. {from_semester} {from_year}. Massachusetts Institute of Technology: MIT OpenCourseWare, <a href='https://ocw.mit.edu'>https://ocw.mit.edu.</a> License:<a href='{course_license}'>Creative Commons BY-NC-SA.</a></p><p>For more information about using these materials and the Creative Commons license, see our <a href='https://ocw.mit.edu/terms'>Terms of Use</a>.</p>"
    return citation


def extract_keys_for_course(base_dir, base_json_name, output_files_path=""):
    """
    Finds number of instance of a key in all jsons within a course
    base_dir: directory of course
    base_json_name: first json in directory
    """
    base_dir = get_correct_path(base_dir)
    base_json = load_json_file(base_dir + base_json_name)
    json_files_dict = {}
    key_occurrence_count = {}

    # Load all json's in directory into memory
    for json_file in os.listdir(base_dir):
        json_files_dict[json_file] = load_json_file(base_dir + json_file)

    # Find occurrences of a key in all jsons in current directory
    for key in base_json.keys():
        for k, val in json_files_dict.items():
            if key in val.keys():
                if key in key_occurrence_count:
                    key_occurrence_count[key] += 1
                else:
                    key_occurrence_count[key] = 1
    min_number_to_consider_required = len(json_files_dict.keys())

    # Print results into two separate csv files for required and optional fields only if an output path is supplied
    if output_files_path:
        required_fields_file = open(get_correct_path(output_files_path) + 'required.csv', 'w')
        optional_fields_file = open(get_correct_path(output_files_path) + 'optional.csv', 'w')
        sorted_base_json = OrderedDict(sorted(base_json.items()))
        for k, v in sorted_base_json.items():
            if key_occurrence_count[k] == min_number_to_consider_required:
                required_fields_file.write(k + "," + types[str(type(v))] + ",REQUIRED" + "\n")
            else:
                optional_fields_file.write(k + "," + types[str(type(v))] + ",OPTIONAL" + "\n")
        required_fields_file.close()
        optional_fields_file.close()


def find_all_possible_vals_for_key(base_dir, key="_content_type"):
    """
    Returns a list of all the different content types of all jsons within directory
    base_dir: directory of course
    key: string
    """
    return_values = set()
    base_dir = get_correct_path(base_dir)
    for item in os.listdir(base_dir):
        item = base_dir + item
        if os.path.isdir(item):
            return_values = return_values.union(find_all_possible_vals_for_key(item, key))
        elif is_json(item):
            loaded_json = load_json_file(item)
            if loaded_json and loaded_json.get(key):
                return_values.add(loaded_json[key])
    return return_values


def find_all_values(base_dir, key="language"):
    base_dir = get_correct_path(base_dir)
    result = set()
    for root, dirs, files in os.walk(base_dir):
        if is_course_directory(root) and files:
            for file in files:
                loaded_json = load_json_file(root + "/" + file)
                if loaded_json and loaded_json[key]:
                    result.add(loaded_json[key])
    return result


def check_key_existence(base_dir, key="unique_id"):
    """
    Searches for a key in all jsons in directory and subdirs. Returns a list of paths
    to JSONs that don't have the passed key.
    If the returned array has 0 elements that means the passed key exist in all examined JSONs

    base_dir: directory
    key: string
    """
    return_values = []
    base_dir = get_correct_path(base_dir)
    for item in os.listdir(base_dir):
        item = base_dir + item
        if os.path.isdir(item):
            return_values = return_values + check_key_existence(item, key)
        elif is_json(item):
            loaded_json = load_json_file(item)
            if loaded_json and key not in loaded_json:
                return_values.append(item)
    return return_values


def find_largest_json(base_dir, result, name=""):
    """
    Find the largest json in directory (largest refers to json with highest number of keys)
    base_dir: directory of course
    result: a list contains the results once function finish
    """
    base_dir = get_correct_path(base_dir)
    for item in os.listdir(base_dir):
        item = base_dir + item
        if os.path.isdir(item):
            find_largest_json(item, result, name)
        else:
            if (name and item.split("/")[-1] == name) or (not name):
                number_of_keys = len(load_json_file(item).keys())
                if number_of_keys > result[1]:
                    result[0] = item
                    result[1] = number_of_keys


def find_largest_sub_dir(base_dir, result):
    base_dir = get_correct_path(base_dir)
    for item in os.listdir(base_dir):
        item = base_dir + item
        if os.path.isdir(item):
            find_largest_sub_dir(item, result)
        else:
            if len(os.listdir(base_dir)) > result[0]:
                result[0] = len(os.listdir(base_dir))
                result[1] = item


def is_course_directory(path_of_course):
    """
    Courses are 5 levels deep after PROD or QA root directories, we use that information
    to confirm whether passed directory is in fact a course.
    """
    def _is_course(path):
        return len(path.split("/")) == 5
    
    ROOT_PROD = "/PROD/"
    ROOT_QA = "/QA/"
    if ROOT_PROD in path_of_course:
        return _is_course(path_of_course.split(ROOT_PROD)[1])
    elif ROOT_QA in path_of_course:
        return _is_course(path_of_course.split(ROOT_QA)[1])
    

def is_json(path_to_file):
    return path_to_file.split("/")[-1].split(".")[1] == "json"


def get_correct_path(directory):
    return directory if directory[-1] == "/" else directory + "/"


def load_json_file(path):
    with open(path, 'r') as f:
        try:
            loaded_json = json.load(f)
            return loaded_json
        except json.JSONDecodeError:
            print("\x1b[0;33;40m Warning:\x1b[0m Failed to load " + path)


def assume_duplicate_keys(loaded_json, list_of_keys):
    result_set = set()
    for key in list_of_keys:
        result_set.add(loaded_json[key])
    return len(result_set) == 1


def dump_dict(destination, name, data):
    destination = get_correct_path(destination)
    with open(destination + name, "w") as f:
        json.dump(data, f)


def safe_get_value(jsons, index, key, path_of_course):
    if jsons[index].get(key):
        return jsons[index].get(key)
    else:
        message = "key \x1b[0;37;40m" + key + "\x1b[0m not found in: " + path_of_course + str(index+1) + ".json"
        print_error(message)


def _safe_get(json, key, json_file_name, path_of_course):
    if json.get(key):
        return json[key]
    else:
        print("\x1b[0;31;40m Error: " + key + "\x1b[0m key not found in: " +
              path_of_course + json_file_name + ".json")


def print_error(message):
    print("\x1b[0;31;40m Error:\x1b[0m " + message)


def print_success(message):
    print("\x1b[0;32;40m Success:\x1b[0m " + message)



#################################################################################
#################################################################################



def course_base_dict():
    return {
        "uid": "",
        "title": "",
        "description": "",
        "citation": "",
        "batch_number": "",
        "filemaker_record_id": "",
        "sort_as": "",
        "department_number": "",
        "master_course_number": "",
        "from_semester": "",
        "from_year": "",
        "to_semester": "",
        "to_year": "",
        "course_owner": "",
        "course_level": "",
        "chp_display_level": "",
        "url": "",
        "short_url": "",
        "language": "",
        "aggregation_level": "",
        "instructors": [],
        "cross_listed_courses": [],
        "contributors_metadata": [],
        "technical_requirements": [],
        "rights": "",
        "license": "",
        "classification": [],
        "subject_keywords": "",
    }


def get_course_sub_page_dict(json, json_file_name, path_of_course):
    return {
        "uid": _safe_get(json, "_uid", json_file_name, path_of_course),
        "parent_uid": _safe_get(json, "parent_uid", json_file_name, path_of_course),
        "title": _safe_get(json, "title", json_file_name, path_of_course),
        "text": _safe_get(json, "text", json_file_name, path_of_course),
        "url": _safe_get(json, "technical_location", json_file_name, path_of_course).split("ocw.mit.edu")[1],
        "short_url": _safe_get(json, "id", json_file_name, path_of_course),
        "aggregation_level": _safe_get(json, "aggregationlevel", json_file_name, path_of_course),
        "subject_keywords": _safe_get(json, "subject", json_file_name, path_of_course),
        "publisher": _safe_get(json, "publisher", json_file_name, path_of_course),
        "language": _safe_get(json, "language", json_file_name, path_of_course),
        "license": _safe_get(json, "license", json_file_name, path_of_course),
        "rights": _safe_get(json, "rights", json_file_name, path_of_course),
        "description": _safe_get(json, "description", json_file_name, path_of_course),
        "type": _safe_get(json, "_type", json_file_name, path_of_course),
        "location": _safe_get(json, "location", json_file_name, path_of_course),
        "content_type": _safe_get(json, "_content_type", json_file_name, path_of_course)
    }


def get_media_dict(json, json_file_name, path_of_course):
    return {
        "uid": _safe_get(json, "_uid", json_file_name, path_of_course),
        "parent_uid": _safe_get(json, "parent_uid", json_file_name, path_of_course),
        "title": _safe_get(json, "title", json_file_name, path_of_course),
        "url": _safe_get(json, "technical_location", json_file_name, path_of_course).split("ocw.mit.edu")[1],
        "short_url": _safe_get(json, "id", json_file_name, path_of_course),
        "section_identifier": _safe_get(json, "section_identifier", json_file_name, path_of_course),
        "creation_date": _safe_get(json, "creation_date", json_file_name, path_of_course),
        "language": _safe_get(json, "language", json_file_name, path_of_course),
        "rights": _safe_get(json, "rights", json_file_name, path_of_course),
        "caption": _safe_get(json, "caption", json_file_name, path_of_course),
        "content_type": _safe_get(json, "_content_type", json_file_name, path_of_course),
        "description": _safe_get(json, "description", json_file_name, path_of_course),
        "alternate_text": _safe_get(json, "alternate_text", json_file_name, path_of_course),
        "credit": _safe_get(json, "credit", json_file_name, path_of_course),
        "other_platform_requirements": _safe_get(json, "other_platform_requirements", json_file_name, path_of_course),
        "license": _safe_get(json, "license", json_file_name, path_of_course),
        "modification_date": _safe_get(json, "modification_date", json_file_name, path_of_course),
        "aggregation_level": _safe_get(json, "aggregationlevel", json_file_name, path_of_course)
    }


def cross_listed_course():
    return {
        "course_number": "",
        "course_level": "",
        "sort_as": ""
    }


def contributor():
    return {
        "uid": "",
        "entity": "McCants, ",
        "hide": "",
        "special_title": "",
        "role": ""
    }


def requirement():
    return {
        "software_type": "",
        "software_name": "",
        "minimum_version": "",
        "maximum_version": ""
    }


def classification():
    return {
        "source": "",
        "id": "",
        "description": ""
    }


NON_COURSE_DIRECTORIES = [
    "PROD/biology/",
    "PROD/chemistry/",
    "PROD/engineering/",
    "PROD/humanities-and-social-sciences/",
    "PROD/iit-jee/",
    "PROD/mathematics/",
    "PROD/more/",
    "PROD/physics/",
    "QA/do-not-publish/",
    "QA/engineering/",
]
EXCLUDED_TYPES = ["text/plain", "text/html"]
ALL_ACCEPTED_MEDIA_TYPES = [
    "image/jpeg",
    "application/pdf",
    "video/x-msvideo",
    "image/png",
    "image/gif",
    "application/msword",
    "application/zip",
    "text/python-source",
    "application/vnd.ms-excel",
    "application/x-subrip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/vnd.dwg",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
    "text/xml",
    "chemical/x-mopac-input",
    "application/rtf",
    "application/vnd.ms-powerpoint",
    "audio/mpeg",
    "application/octet-stream",
    "video/quicktime",
    "text/x-fortran",
    "video/mpeg",
    "text/x-objcsrc",
    "application/x-shockwave-flash",
    "application/postscript",
    "application/x-tar",
    "application/x-gzip",
    "application/java-archive",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "chemical/x-pdb",
    "text/comma-separated-values",
    "application/x-xfig",
    "text/x-tex",
    "application/x-dvi",
    "application/x-bzip",
    "text/x-csrc",
    "image/tiff",
    "audio/x-wav",
    "image/x-photoshop",
    "audio/x-ape",
    "application/x-gameboy-rom",
    "application/x-ms-dos-executable",
    "text/x-java",
    "application/javascript",
    "application/x-java-jnlp-file",
    "application/x-msdos-program",
    "application/x-executable",
    "text/x-scheme",
    "text/x-c++src",
    "application/mathematica",
    "image/x-ms-bmp",
    "audio/x-riff",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/rar",
    "text/x-sql",
    "image/svg+xml",
    "video/mp4",
    "application/ni",
    "audio/midi",
    "audio/x-aiff",
    "video/x-ms-wmv",
    "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
    "chemical/x-xyz",
    "text/x-chdr",
    "application/vnd.sun.xml.draw.template",
    "application/x-object",
    "application/x-shellscript",
    "text/x-csh",
    "text/x-pascal",
    "application/x-stuffit",
    "application/x-rar",
    "application/x-cdf"
]
types = {
    "<class 'str'>": "String",
    "<class 'int'>": "Int",
    "<class 'list'>": "List",
    "<class 'dict'>": "Dictionary",
    "<class 'bool'>": "Boolean",
}
types_dict = {
    "image/jpeg": [],
    "application/pdf": [],
    "video/x-msvideo": [],
    "image/png": [],
    "image/gif": [],
    "application/msword": [],
    "application/zip": [],
    "text/python-source": [],
    "application/vnd.ms-excel": [],
    "application/x-subrip": [],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [],
    "image/vnd.dwg": [],
    "application/vnd.ms-excel.sheet.macroEnabled.12": [],
    "text/xml": [],
    "chemical/x-mopac-input": [],
    "application/rtf": [],
    "application/vnd.ms-powerpoint": [],
    "audio/mpeg": [],
    "application/octet-stream": [],
    "video/quicktime": [],
    "text/x-fortran": [],
    "video/mpeg": [],
    "text/x-objcsrc": [],
    "application/x-shockwave-flash": [],
    "application/postscript": [],
    "application/x-tar": [],
    "application/x-gzip": [],
    "application/java-archive": [],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [],
    "chemical/x-pdb": [],
    "text/comma-separated-values": [],
    "application/x-xfig": [],
    "text/x-tex": [],
    "application/x-dvi": [],
    "application/x-bzip": [],
    "text/x-csrc": [],
    "image/tiff": [],
    "audio/x-wav": [],
    "image/x-photoshop": [],
    "audio/x-ape": [],
    "application/x-gameboy-rom": [],
    "application/x-ms-dos-executable": [],
    "text/x-java": [],
    "application/javascript": [],
    "application/x-java-jnlp-file": [],
    "application/x-msdos-program": [],
    "application/x-executable": [],
    "text/x-scheme": [],
    "text/x-c++src": [],
    "application/mathematica": [],
    "image/x-ms-bmp": [],
    "audio/x-riff": [],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": [],
    "application/rar": [],
    "text/x-sql": [],
    "image/svg+xml": [],
    "video/mp4": [],
    "application/ni": [],
    "audio/midi": [],
    "audio/x-aiff": [],
    "video/x-ms-wmv": [],
    "application/vnd.ms-excel.sheet.binary.macroEnabled.12": [],
    "chemical/x-xyz": [],
    "text/x-chdr": [],
    "application/vnd.sun.xml.draw.template": [],
    "application/x-object": [],
    "application/x-shellscript": [],
    "text/x-csh": [],
    "text/x-pascal": [],
    "application/x-stuffit": [],
    "application/x-rar": [],
    "application/x-cdf": []
}
missing_binary_data_media_jsons = copy.deepcopy(types_dict)