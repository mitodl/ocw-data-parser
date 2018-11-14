"""OCW Data Parser

Usage:
    ocw_data_parser.py ROOT_DIR

"""
from utils import is_json, get_correct_path, load_json_file, dump_dict, safe_get_value, \
    is_course_directory, print_error, print_success, compose_pages
from media_extractor import compose_and_extract_media
from docopt import docopt
import os


# todo: change the not_course output to a list
# todo: handle courses with more than 1000 JSONs
# todo: do the try except for specific keys
# todo: refactor safe_get_value to have PRINTing option that defaults to False
# todo: tree view (maybe)
def ocw_parse_all(root_dir):
    root_dir = get_correct_path(root_dir)
    course_counter = 0
    f = open("/Users/method/Desktop/not_courses.txt", "w")
    for root, dirs, files in os.walk(root_dir):
        if not is_course_directory(root) and not dirs:
            message = "directory is not a course " + root
            print_error(message)
            f.write(root + "\n")
        elif is_course_directory(root) and isinstance(root[-1], int) and files:
            course_counter += 1
            # generate_output_for_course(root)
    f.close()
    print_success("Number of parsed courses is: " + str(course_counter))


def generate_output_for_course(path_of_course, destination):
    """ Generates summary JSON file and extracts media for a single OCW course """
    path_of_course = get_correct_path(path_of_course)
    destination = get_correct_path(destination)

    # Get all JSONs in directory and sort them
    sorted_course_jsons = []
    for file in os.listdir(path_of_course):
        if is_json(file):
            sorted_course_jsons.append(int(file.split(".")[0]))
    sorted_course_jsons = sorted(sorted_course_jsons)
    loaded_jsons = []

    # Load JSONs into memory
    for course_number in sorted_course_jsons:
        file_name = str(course_number) + ".json"
        lj = load_json_file(path_of_course + file_name)
        if lj:
            loaded_jsons.append(lj)
        else:
            print("Error loading the following json: " + path_of_course + file_name)

    # Create a directory
    destination = destination + loaded_jsons[0]["id"]
    os.makedirs(destination, exist_ok=True)

    # Generate summary JSON
    new_json = dict()
    new_json["uid"] = safe_get_value(loaded_jsons, 0, "_uid", path_of_course)
    new_json["title"] = safe_get_value(loaded_jsons, 0, "title", path_of_course)
    new_json["description"] = safe_get_value(loaded_jsons, 1, "description", path_of_course)
    master_course = safe_get_value(loaded_jsons, 0, "master_course_number", path_of_course)
    new_json["department_number"] = master_course.split('.')[0]
    new_json["master_course_number"] = master_course.split('.')[1]
    new_json["from_semester"] = safe_get_value(loaded_jsons, 0, "from_semester", path_of_course)
    new_json["from_year"] = safe_get_value(loaded_jsons, 0, "from_year", path_of_course)
    new_json["to_semester"] = safe_get_value(loaded_jsons, 0, "to_semester", path_of_course)
    new_json["to_year"] = safe_get_value(loaded_jsons, 0, "to_year", path_of_course)
    new_json["course_owner"] = safe_get_value(loaded_jsons, 0, "course_owner", path_of_course)
    new_json["course_level"] = safe_get_value(loaded_jsons, 0, "course_level", path_of_course)
    new_json["url"] = safe_get_value(loaded_jsons, 0, "technical_location", path_of_course).split("ocw.mit.edu")[1]
    new_json["short_url"] = safe_get_value(loaded_jsons, 0, "id", path_of_course)
    new_json["subject_keywords"] = safe_get_value(loaded_jsons, 0, "subject", path_of_course)
    new_json["instructors"] = safe_get_value(loaded_jsons, 0, "instructors", path_of_course)
    new_json["language"] = safe_get_value(loaded_jsons, 0, "language", path_of_course)
    new_json["linked_pages"] = compose_pages(loaded_jsons, path_of_course)
    new_json["linked_media"] = compose_and_extract_media(loaded_jsons, path_of_course, destination)

    # Some excluded keys. Delete after discussion.
    # new_json["citation"] = compose_citation(loaded_jsons)
    # new_json["batch_number"] = safe_get_value(loaded_jsons, 0, "ocw_batch_id", path_of_course)
    # new_json["filemaker_record_id"] = safe_get_value(loaded_jsons, 0, "fm_record_id", path_of_course)
    # new_json["sort_as"] = safe_get_value(loaded_jsons, 0, "sort_as", path_of_course)
    # new_json["chp_display_level"] = safe_get_value(loaded_jsons, 0, "chp_display_level", path_of_course)
    # new_json["aggregation_level"] = safe_get_value(loaded_jsons, 0, "aggregationlevel", path_of_course)
    # new_json["rights"] = safe_get_value(loaded_jsons, 0, "rights", path_of_course)
    # new_json["license"] = safe_get_value(loaded_jsons, 0, "license", path_of_course)
    # new_json["publisher"] = safe_get_value(loaded_jsons, 0, "publisher", path_of_course)
    # new_json["publication_date"] = safe_get_value(loaded_jsons, 0, "first_published_to_production", path_of_course)

    dump_dict(destination, "course_summary.json", new_json)


if __name__ == "__main__":
    arguments = docopt(__doc__)
    ocw_parse_all(arguments['ROOT_DIR'])
