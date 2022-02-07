"""Tests for OCWParser"""

import json
import logging
import os
from base64 import b64decode
from copy import deepcopy
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from unittest.mock import patch, ANY

from requests.exceptions import HTTPError
import responses
import pytest
from webvtt.errors import MalformedFileError

from ocw_data_parser.ocw_data_parser import OCWParser, load_raw_jsons
from ocw_data_parser.utils import update_srt_to_vtt
import ocw_data_parser.test_constants as constants

log = logging.getLogger(__name__)


# pylint: disable=unused-argument
def test_no_params(ocw_parser):
    """
    Test that an OCWParser with no params raises an exception
    """
    with pytest.raises(Exception):
        OCWParser()


def test_parser_loaded_jsons(ocw_parser):
    """
    Test instantiating a parser with preloaded jsons
    """
    assert OCWParser(
        loaded_jsons=ocw_parser.jsons
    ), "instantiating parser with preloaded jsons failed"


def test_parser_invalid_file(ocw_parser):
    """
    Test instantiating a parser with an improperly named json file in the source directory
    """
    with TemporaryDirectory() as destination_dir:
        with open(os.path.join(constants.SINGLE_COURSE_DIR, "jsons/test.json"), "w"):
            with pytest.raises(ValueError):
                OCWParser(
                    course_dir=constants.SINGLE_COURSE_DIR,
                    destination_dir=destination_dir,
                    static_prefix=constants.STATIC_PREFIX,
                )
            os.remove(os.path.join(constants.SINGLE_COURSE_DIR, "jsons/test.json"))


def test_generate_parsed_json_none_source(ocw_parser):
    """
    Make sure that running generate_parsed_json doesn't throw an error after nulling
    out the parser's source jsons
    """
    ocw_parser.jsons = None
    ocw_parser.generate_parsed_json()
    assert ocw_parser.jsons is not None


def test_generate_parsed_json_none_course_image_uid(ocw_parser):
    """
    Make sure course_image_uid is regenerated by generate_parsed_json after it's nulled out
    """
    ocw_parser.course_image_uid = None
    ocw_parser.generate_parsed_json()
    assert ocw_parser.course_image_uid is not None


def test_load_raw_jsons_invalid_file(ocw_parser):
    """
    Add a json file with invalid content to the course_dir and make sure it generates an error
    """
    with TemporaryDirectory() as destination_dir:
        with open(
            os.path.join(constants.SINGLE_COURSE_DIR, "jsons/999.json"), "w"
        ) as file:
            file.write("{")
        with pytest.raises(json.decoder.JSONDecodeError):
            OCWParser(
                course_dir=constants.SINGLE_COURSE_DIR,
                destination_dir=destination_dir,
                static_prefix=constants.STATIC_PREFIX,
            )
        os.remove(os.path.join(constants.SINGLE_COURSE_DIR, "jsons/999.json"))


def test_load_raw_jsons():
    """Test that load_raw_jsons """
    with TemporaryDirectory() as project_dir:
        for num in range(1, 4000):
            group = int(num / 1000)
            parent_dir = Path(project_dir) / str(group)
            os.makedirs(parent_dir, exist_ok=True)
            filepath = parent_dir / f"{num}.json"

            with open(filepath, "w") as file:
                file.write('{"a":2,"b":3,"c":4}')

        jsons = load_raw_jsons(project_dir)

    assert [_json["order_index"] for _json in jsons] == list(range(1, 4000))


def test_upload_all_data_to_s3(ocw_parser_s3, s3_bucket):
    """
    Use moto (mock boto) to test s3 uploading
    """
    ocw_parser_s3.upload_all_media_to_s3(upload_parsed_json=True)
    parsed_json = ocw_parser_s3.get_parsed_json()

    for page in parsed_json["course_pages"]:
        if page["text"]:
            for bucket_item in s3_bucket.objects.filter(
                Prefix=ocw_parser_s3.s3_target_folder
            ):
                if bucket_item.key in page["file_location"]:
                    assert (
                        bucket_item.key
                        == f"{ocw_parser_s3.s3_target_folder}{page['uid']}_{page['short_url']}.html"
                    )
    for course_file in parsed_json["course_files"]:
        for bucket_item in s3_bucket.objects.filter(
            Prefix=ocw_parser_s3.s3_target_folder
        ):
            if bucket_item.key in course_file["file_location"]:
                assert (
                    bucket_item.key
                    == f"{ocw_parser_s3.s3_target_folder}{course_file['uid']}_{course_file['id']}"
                )

        if course_file["uid"] == ocw_parser_s3.course_image_uid:
            assert (
                parsed_json["image_src"]
                == f'{s3_upload_base()}{course_file["uid"]}_{course_file["id"]}'
            )
            assert parsed_json["image_description"] == course_file["description"]
        elif course_file["uid"] == ocw_parser_s3.course_thumbnail_image_uid:
            assert (
                parsed_json["thumbnail_image_src"]
                == f'{s3_upload_base()}{course_file["uid"]}_{course_file["id"]}'
            )
            assert (
                parsed_json["thumbnail_image_description"] == course_file["description"]
            )

    for bucket_item in s3_bucket.objects.filter(Prefix=ocw_parser_s3.s3_target_folder):
        if (
            bucket_item.key
            == f'{ocw_parser_s3.s3_target_folder}{parsed_json["short_url"]}_parsed.json'
        ):
            parsed_json_key = bucket_item.key
    assert parsed_json_key is not None

    assert parsed_json["image_src"] is not None
    assert parsed_json["thumbnail_image_src"] is not None


def test_upload_all_data_to_s3_no_binary_data(ocw_parser_s3, caplog):
    """
    Test that there is a descriptive error message when there is no binary data in a json file
    """
    with patch("ocw_data_parser.ocw_data_parser.get_binary_data", return_value=None):
        ocw_parser_s3.upload_all_media_to_s3()
        assert (
            "Could not load binary data for file 9dbd5e22e2379a1bb4e844757c445dfd_7UJ4CFRGd-U.srt "
            "in json file 15.json for course 18-06-linear-algebra-spring-2010"
            in [rec.message for rec in caplog.records]
        )


def test_upload_all_data_to_s3_large_media_link_upload_error(
    mocker, ocw_parser_s3, caplog
):
    """
    Test that there is a descriptive error message when a large media file cannot be uploaded
    """
    get_mock = mocker.patch("requests.get")
    get_mock.return_value.raise_for_status.side_effect = HTTPError()
    ocw_parser_s3.upload_all_media_to_s3()
    assert (
        "Could NOT upload powerMethod.html for course 18-06-linear-algebra-spring-2010 "
        "from link http://ocw.mit.edu/ans7870/18/18.06/javademo/power_method_applet/powerMethod.html"
        in [rec.message for rec in caplog.records]
    )


def test_upload_parsed_json_to_s3_no_short_url(ocw_parser_s3, s3_bucket, caplog):
    """
    Test that there is a descriptive error message when the parsed json has no uid

    """
    ocw_parser_s3.parsed_json["short_url"] = None
    with pytest.raises(Exception) as ex:
        ocw_parser_s3.upload_parsed_json_to_s3(s3_bucket)
    assert str(ex.value) == "No short_url found in parsed_json"


@responses.activate
def test_upload_course_image(ocw_parser_s3, s3_bucket):
    """
    Use moto (mock boto) to test s3 uploading
    """
    ocw_parser_s3.upload_course_image()
    parsed_json = ocw_parser_s3.get_parsed_json()

    found_image_keys = []
    found_parsed_json = False
    for bucket_item in s3_bucket.objects.filter(Prefix=ocw_parser_s3.s3_target_folder):
        if (
            bucket_item.key
            == ocw_parser_s3.s3_target_folder
            + parsed_json["short_url"]
            + "_parsed.json"
        ):
            found_parsed_json = True
        if bucket_item.key in [
            ocw_parser_s3.s3_target_folder + os.path.basename(parsed_json[key])
            for key in ["image_src", "thumbnail_image_src"]
        ]:
            found_image_keys.append(bucket_item.key)

    assert len(found_image_keys) == 2
    assert found_parsed_json is True

    assert ocw_parser_s3.parsed_json["image_src"] is not None
    assert ocw_parser_s3.parsed_json["thumbnail_image_src"] is not None

    for course_file in parsed_json["course_files"]:
        if course_file["uid"] == ocw_parser_s3.course_image_uid:
            assert (
                parsed_json["image_src"]
                == f'{s3_upload_base()}{course_file["uid"]}_{course_file["id"]}'
            )
            assert parsed_json["image_description"] == course_file["description"]
        elif course_file["uid"] == ocw_parser_s3.course_thumbnail_image_uid:
            assert (
                parsed_json["thumbnail_image_src"]
                == f'{s3_upload_base()}{course_file["uid"]}_{course_file["id"]}'
            )
            assert (
                parsed_json["thumbnail_image_description"] == course_file["description"]
            )
        else:
            assert course_file["file_location"]


def test_upload_course_image_no_s3_bucket_name(ocw_parser_s3, caplog):
    """
    Test that uploading the course image without the s3 bucket name throws an error
    """
    ocw_parser_s3.s3_bucket_name = None
    with pytest.raises(ValueError):
        ocw_parser_s3.upload_course_image()
        assert ["Please set your s3 bucket name"] == [
            rec.message for rec in caplog.records
        ]


def test_get_parsed_json(ocw_parser):
    """
    Test that getting the parsed JSON is not None or empty or missing basic properties
    and doesn't throw an exception
    """
    fail_template = "failed to read {} property from parsed json"
    parsed_json = ocw_parser.get_parsed_json()
    assert parsed_json, "failed to get parsed json"
    assert parsed_json["uid"], fail_template.format("uid")
    assert parsed_json["title"], fail_template.format("title")
    assert parsed_json["description"], fail_template.format("description")
    assert parsed_json["short_url"], fail_template.format("short_url")
    assert len(parsed_json["open_learning_library_related"]) == 3, fail_template.format(
        "open_learning_library_related"
    )
    assert (
        parsed_json["open_learning_library_related"][0]["url"]
        == "https://openlearninglibrary.mit.edu/courses/course-v1:MITx+18.01.1x+2T2019/about"
    )


def test_export_parsed_json_s3_links(ocw_parser_s3):
    """
    Test that exporting the parsed json file with s3 links doesn't error
    """
    ocw_parser_s3.export_parsed_json(s3_links=True)
    json_path = os.path.join(
        ocw_parser_s3.destination_dir,
        "{}_parsed.json".format(ocw_parser_s3.parsed_json["short_url"]),
    )
    assert os.path.exists(json_path) and os.path.getsize(json_path) > 0


def test_export_parsed_json_no_s3_bucket_name(ocw_parser_s3, caplog):
    """
    Test that exporting the parsed json file without an s3 bucket name throws an error
    """
    ocw_parser_s3.s3_bucket_name = None
    ocw_parser_s3.export_parsed_json(s3_links=True)
    assert ["Please set your s3 bucket name"] == [rec.message for rec in caplog.records]


def test_set_s3_bucket_name(ocw_parser_s3):
    """
    Test setting the s3 bucket name
    """
    assert ocw_parser_s3.s3_bucket_name == "testing"


def test_set_s3_access_key(ocw_parser_s3):
    """
    Test setting the s3 access key
    """
    assert ocw_parser_s3.s3_bucket_access_key == "testing"


def test_set_s3_secret_access_key(ocw_parser_s3):
    """
    Test setting the s3 secret access key
    """
    assert ocw_parser_s3.s3_bucket_secret_access_key == "testing"


def test_set_s3_target_folder(ocw_parser_s3):
    """
    Test setting the s3 target folder
    """
    assert ocw_parser_s3.s3_target_folder == "course-1"


def s3_upload_base():
    """Fake URL base for S3"""
    return "https://testing.s3.amazonaws.com/course-1/"


def test_uid(ocw_parser, course_id):
    """
    Test that the uid property of the parsed JSON matches the uid of the course site root
    """
    ocw_parser.export_parsed_json()
    with open(
        os.path.join(constants.SINGLE_COURSE_DIR, "jsons/1.json"), "r"
    ) as first_json:
        first_json_data = json.loads(first_json.read())
        with open(
            os.path.join(
                ocw_parser.destination_dir, "{}_parsed.json".format(course_id)
            ),
            "r",
        ) as parsed_json:
            parsed_json_data = json.loads(parsed_json.read())
            assert first_json_data["_uid"] == parsed_json_data["uid"]


def test_highlight_text(ocw_parser, ocw_parser_course_2):
    """ Test that highlight_text makes it into parsed json with correct values"""
    assert ocw_parser.parsed_json["highlights_text"].startswith(
        "<p>This course parallels"
    )
    assert ocw_parser_course_2.parsed_json["highlights_text"] == ""


def test_related_content(ocw_parser, ocw_parser_course_2):
    """ Test that related_content makes it into parsed json with correct values"""
    assert ocw_parser.parsed_json["related_content"] == "some related content"
    assert ocw_parser_course_2.parsed_json["related_content"] == ""


def test_course_files(ocw_parser):
    """Make sure course_files include the right fields with the correct default values"""
    assert len(ocw_parser.parsed_json["course_files"]) == 172
    assert ocw_parser.parsed_json["course_files"][0] == {
        "order_index": 6,
        "uid": "c24518ecda658185c40c2e5eeb72c7fa",
        "id": "182.png",
        "parent_uid": "3f3b7835cf477d3ba10b05fbe03cbffa",
        "title": "182.png",
        "caption": "",
        "file_type": "image/png",
        "alt_text": "",
        "credit": "",
        "platform_requirements": "",
        "description": "",
        "type": "OCWImage",
        "file_location": "c24518ecda658185c40c2e5eeb72c7fa_182.png",
    }


def test_course_files_s3(ocw_parser_s3):
    """Make sure course_files include the right fields with the correct default values"""
    ocw_parser_s3.generate_parsed_json()
    assert ocw_parser_s3.parsed_json["course_files"][0] == {
        "order_index": 6,
        "uid": "c24518ecda658185c40c2e5eeb72c7fa",
        "id": "182.png",
        "parent_uid": "3f3b7835cf477d3ba10b05fbe03cbffa",
        "title": "182.png",
        "caption": "",
        "file_type": "image/png",
        "alt_text": "",
        "credit": "",
        "platform_requirements": "",
        "description": "",
        "type": "OCWImage",
        "file_location": "https://testing.s3.amazonaws.com/course-1/c24518ecda658185c40c2e5eeb72c7fa_182.png",
    }


def test_course_foreign_files(ocw_parser):
    """Make sure course_foreign_files include the right fields with the correct default values"""
    assert ocw_parser.parsed_json["course_foreign_files"][0] == {
        "link": "http://ocw.mit.edu/ans7870/18/18.06/tools/Applets_sound/uropmovie.html",
        "parent_uid": "b5785e071ddb991cf3dfd7cc469e6397",
    }
    assert len(ocw_parser.parsed_json["course_foreign_files"]) == 20


def test_other_information_text(ocw_parser):
    """other_information_text should be an empty string"""
    assert ocw_parser.parsed_json["other_information_text"] == ""


def test_other_version_parent_uids(ocw_parser):
    """Make sure other_version_parent_subjects includes a list containing one UID"""
    assert (
        ocw_parser.parsed_json["other_version_parent_uids"][0]
        == "c57db32e19cecbfe65656ede124729fb"
    )
    assert len(ocw_parser.parsed_json["other_version_parent_uids"]) == 1


def test_aka_course_number(ocw_parser):
    """Make sure the aka_course_number field is transformed property into new_course_numbers"""
    assert ocw_parser.parsed_json["new_course_numbers"][0] == {
        "new_course_number_col": "18.06TEST",
        "old_course_number_col": "18.06",
        "sort_as_col": "18.06TEST",
        "course_type_col": "Undergraduate",
    }


def test_course_pages(ocw_parser):
    """assert the output of composing course_pages"""
    assert len(ocw_parser.parsed_json["course_pages"]) > 0
    page = ocw_parser.parsed_json["course_pages"][1]
    page_without_text = {**page}
    del page_without_text["text"]
    del page_without_text["description"]
    assert page_without_text == {
        "order_index": 3,
        "uid": "ede17211bd49ea166ed701f09c1de288",
        "parent_uid": "aabc44bdb2e45374d62f30f2a6d4c63e",
        "title": "Syllabus",
        "short_page_title": "Syllabus",
        "type": "CourseSection",
        "is_image_gallery": False,
        "is_media_gallery": False,
        "list_in_left_nav": False,
        "file_location": "ede17211bd49ea166ed701f09c1de288_syllabus.html",
        "short_url": "syllabus",
        "url": "/courses/mathematics/18-06-linear-algebra-spring-2010/syllabus",
        "bottomtext": "<p>Sample Bottom Text</p>",
    }
    assert page["text"].startswith('<h2 class="subhead">Course Meeting Times')
    assert page["description"].startswith(
        "This syllabus section provides information on course goals"
    )


def test_instructor_insights_divided_sections(ocw_parser_course_2):
    """assert that instructor insights pages with divided sections are parsed properly"""
    assert len(ocw_parser_course_2.parsed_json["course_pages"]) > 0
    original_page = ocw_parser_course_2.jsons[5]
    page = ocw_parser_course_2.parsed_json["course_pages"][3]
    page_without_text = deepcopy(page)
    del page_without_text["text"]
    assert page_without_text == {
        "order_index": 6,
        "uid": "1c2cb2ad1c70fd66f19e20103dc94595",
        "parent_uid": "d9aad1541f1a9d3c0f7b0dcf9531a9a1",
        "title": "Instructor Insights",
        "short_page_title": "Instructor Insights",
        "url": "/courses/earth-atmospheric-and-planetary-sciences/12-001-introduction-to-geology-fall-2013/instructor-insights",
        "short_url": "instructor-insights",
        "description": "This section provides insights and information about the course from the instructors.",
        "type": "ThisCourseAtMITSection",
        "is_image_gallery": False,
        "is_media_gallery": False,
        "list_in_left_nav": False,
        "file_location": "1c2cb2ad1c70fd66f19e20103dc94595_instructor-insights.html",
        "bottomtext": "",
    }
    for section in constants.INSTRUCTOR_INSIGHTS_SECTIONS:
        assert original_page.get(section) in page.get("text")


@pytest.mark.parametrize("has_instructors", [True, False])
@pytest.mark.parametrize("has_contributors", [True, False])
def test_instructors(ocw_parser_course_2, has_instructors, has_contributors):
    """
    instructors list should be present as a list in the output, but in the same order as in the
    metadata_contributor_list if present.
    """
    expected_instructors = ocw_parser_course_2.jsons[0]["instructors"]
    contributors_list = ocw_parser_course_2.jsons[0]["metadata_contributor_list"]
    if has_contributors:
        expected_instructors.reverse()
    else:
        ocw_parser_course_2.jsons[0]["metadata_contributor_list"] = None
    if not has_instructors:
        ocw_parser_course_2.jsons[0]["instructors"] = None
    ocw_parser_course_2.generate_parsed_json()
    for instructor in expected_instructors:
        del instructor["mit_id"]
    assert ocw_parser_course_2.parsed_json["instructors"] == (
        expected_instructors if has_instructors else []
    )
    assert ocw_parser_course_2.parsed_json["metadata_contributor_list"] == (
        contributors_list if has_contributors else []
    )


def test_course_features(ocw_parser):
    """assert the output of course_features"""
    assert ocw_parser.parsed_json["course_features"] == [
        {
            "ocw_feature": "AV special element video",
            "ocw_feature_notes": "",
            "ocw_feature_url": "./resolveuid/b5785e071ddb991cf3dfd7cc469e6397",
            "ocw_speciality": "",
            "ocw_subfeature": "Tutorial",
        },
        {
            "ocw_feature": "AV lectures",
            "ocw_feature_notes": "",
            "ocw_feature_url": "./resolveuid/6b1f662457366951bfe85945521b0299",
            "ocw_speciality": "",
            "ocw_subfeature": "Video",
        },
        {
            "ocw_feature": "AV recitations",
            "ocw_feature_notes": "",
            "ocw_feature_url": "./resolveuid/6b1f662457366951bfe85945521b0299",
            "ocw_speciality": "",
            "ocw_subfeature": "",
        },
        {
            "ocw_feature": "Assignments",
            "ocw_feature_notes": "",
            "ocw_feature_url": "./resolveuid/87609dbba9d13a6b234d62de21a20433",
            "ocw_speciality": "",
            "ocw_subfeature": "problem sets with solutions",
        },
        {
            "ocw_feature": "Exams",
            "ocw_feature_notes": "",
            "ocw_feature_url": "./resolveuid/c13c4766c0cf1486f0cf6435c531eaad",
            "ocw_speciality": "",
            "ocw_subfeature": "Solutions",
        },
        {
            "ocw_feature": "Instructor Insights",
            "ocw_feature_notes": "",
            "ocw_feature_url": "./resolveuid/3f3b7835cf477d3ba10b05fbe03cbffa",
            "ocw_speciality": "",
            "ocw_subfeature": "",
        },
    ]


def test_course_feature_tags(ocw_parser):
    """assert the output of course_feature_tags"""
    assert ocw_parser.parsed_json["course_feature_tags"] == [
        {
            "course_feature_tag": "Tutorial Videos",
            "ocw_feature_url": "./resolveuid/b5785e071ddb991cf3dfd7cc469e6397",
        },
        {
            "course_feature_tag": "Lecture Videos",
            "ocw_feature_url": "./resolveuid/6b1f662457366951bfe85945521b0299",
        },
        {
            "course_feature_tag": "Recitation Videos",
            "ocw_feature_url": "./resolveuid/6b1f662457366951bfe85945521b0299",
        },
        {
            "course_feature_tag": "Problem Sets with Solutions",
            "ocw_feature_url": "./resolveuid/87609dbba9d13a6b234d62de21a20433",
        },
        {
            "course_feature_tag": "Exams with Solutions",
            "ocw_feature_url": "./resolveuid/c13c4766c0cf1486f0cf6435c531eaad",
        },
    ]


def test_tags(ocw_parser):
    """assert tags output"""
    expected_tags = [
        "matrix theory",
        "linear algebra",
        "systems of equations",
        "vector spaces",
        "determinants",
        "eigenvalues",
        "similarity",
        "positive definite matrices",
        "least-squares approximations",
        "stability of differential equations",
        "networks",
        "Fourier transforms",
        "Markov processes",
    ]
    assert ocw_parser.parsed_json["tags"] == [{"name": tag} for tag in expected_tags]


def test_course_embedded_media(ocw_parser):
    """assert embedded media"""
    assert len(ocw_parser.parsed_json["course_embedded_media"]) == 36
    key = "12700054aninterviewwithgilbertstrangonteachinglinearalgebra63021644"
    media_json = {**ocw_parser.parsed_json["course_embedded_media"][key]}
    transcript = media_json["transcript"]
    del media_json["transcript"]
    embedded_media = media_json["embedded_media"]
    del media_json["embedded_media"]
    assert media_json == {
        "about_this_resource_text": "",
        "inline_embed_id": "12700054aninterviewwithgilbertstrangonteachinglinearalgebra63021644",
        "order_index": 10,
        "parent_uid": "3f3b7835cf477d3ba10b05fbe03cbffa",
        "related_resources_text": "",
        "optional_text": "optional text",
        "optional_tab_title": "optional tab title",
        "resource_index_text": "resource index text",
        "short_url": "an-interview-with-gilbert-strang-on-teaching-linear-algebra",
        "technical_location": "https://ocw.mit.edu/courses/mathematics/18-06-linear-algebra-spring-2010/instructor-insights/an-interview-with-gilbert-strang-on-teaching-linear-algebra",
        "title": "An Interview with Gilbert Strang on Teaching Linear Algebra",
        "uid": "e21b71ff0fa975bfa9acb2a155aafc1d",
        "template_type": "Embed",
    }
    assert transcript.startswith("<p><span m='6840'>SARAH HANSEN:")
    assert len(embedded_media) == 11
    assert embedded_media[1] == {  # important because it has a technical_location
        "id": "18.06.jpg",
        "parent_uid": "e21b71ff0fa975bfa9acb2a155aafc1d",
        "technical_location": "https://ocw.mit.edu/courses/mathematics/18-06-linear-algebra-spring-2010/instructor-insights/an-interview-with-gilbert-strang-on-teaching-linear-algebra/18.06.jpg",
        "title": "18.06.jpg",
        "type": None,
        "uid": "f777380de6feec2c42ab6e159e05ddf2",
    }
    assert embedded_media[2] == {  # important because it has a media_location
        "id": "Thumbnail-YouTube-JPG",
        "media_location": "https://img.youtube.com/vi/7UJ4CFRGd-U/default.jpg",
        "parent_uid": "e21b71ff0fa975bfa9acb2a155aafc1d",
        "title": "Thumbnail-YouTube-JPG",
        "type": "Thumbnail",
        "uid": "7cd0685535147aebd9d7c2e98dc68afd",
    }


def test_foreign_files(ocw_parser):
    """assert course_foreign_files output"""
    assert len(ocw_parser.parsed_json["course_foreign_files"]) == 20
    assert ocw_parser.parsed_json["course_foreign_files"][0] == {
        "link": "http://ocw.mit.edu/ans7870/18/18.06/tools/Applets_sound/uropmovie.html",
        "parent_uid": "b5785e071ddb991cf3dfd7cc469e6397",
    }


def test_extract_media_locally(ocw_parser):
    """extract_media_locally should write media files to a local directory"""
    ocw_parser.extract_media_locally()
    static_files = Path(ocw_parser.destination_dir) / "output" / "static_files"
    for path in static_files.iterdir():
        assert path.stat().st_size > 0  # make sure files are non-trivial

    expected_counts = {
        ".pdf": 93,
        ".srt": 36,
        ".html": 12,
        ".jpg": 42,
        ".png": 1,
    }
    counts = {}
    for path in static_files.iterdir():
        ext = os.path.splitext(path)[1]
        if ext not in counts:
            counts[ext] = 0
        counts[ext] += 1
    assert counts == expected_counts


def test_populate_vtt_files(ocw_parser):
    """populate_vtt_files should duplicate srt content files"""
    subrip_count = 0
    srt_json = {}
    with open(
        "ocw_data_parser/test_json/course_dir/captions_example.json", "rb"
    ) as file:
        datafield = json.load(file)
        for loaded_json in ocw_parser.jsons:
            if loaded_json["_content_type"] == "application/x-subrip":
                loaded_json["_datafield_file"] = datafield
                subrip_count += 1
                if subrip_count == 1:
                    srt_json = loaded_json
    files_count_before = len(ocw_parser.jsons)
    ocw_parser.populate_vtt_files()
    assert files_count_before + subrip_count == len(ocw_parser.jsons)

    vtt_file_id = update_srt_to_vtt(srt_json["id"])
    vtt_json = next(
        (new_json for new_json in ocw_parser.jsons if new_json["id"] == vtt_file_id),
        None,
    )
    assert len(b64decode(vtt_json["_datafield_file"]["data"])) == 87102
    assert vtt_json["_uid"] == "2f2b1bbc318b5fdcade8ac2ec1b5a911"


@pytest.mark.parametrize(
    "exception, expected_args",
    [
        [KeyError(), ("Unknown error when converting vtt %s", ANY)],
        [
            MalformedFileError(),
            ("This file is malformed and cannot be converted to vtt %s. %s", ANY, ANY),
        ],
    ],
)
def test_populate_vtt_files_error(ocw_parser, mocker, exception, expected_args):
    """populate_vtt_files should log errors and continue"""
    mock_exception = mocker.patch("ocw_data_parser.utils.log.exception")
    mocker.patch("webvtt.from_srt", side_effect=exception)
    ocw_parser.populate_vtt_files()
    mock_exception.assert_any_call(*expected_args)


def test_extract_foreign_media_locally(ocw_parser):
    """
    extract_foreign_media_locally should download and save foreign media files
    """
    with TemporaryDirectory() as tempdir:
        tempdir = Path(tempdir)
        ocw_parser.destination_dir = tempdir
        ocw_parser.extract_foreign_media_locally()

        static_files_dir = tempdir / "output" / "static_files"
        with open(static_files_dir / "eigen_lecture_1.html") as file:
            assert len(file.read()) == 839
        assert len(list(static_files_dir.iterdir())) == 20


def test_extract_foreign_media_locally_error(ocw_parser, mocker, caplog):
    """
    extract_foreign_media_locally should log and continue if there is an error
    """
    get_mock = mocker.patch("requests.get")
    get_mock.return_value.content = b"somebytes"
    first = True

    def _raise_side_effect():
        """Helper function to only error once"""
        nonlocal first
        if first:
            first = False
            raise HTTPError()

    get_mock.return_value.raise_for_status.side_effect = _raise_side_effect
    with TemporaryDirectory() as tempdir:
        tempdir = Path(tempdir)
        ocw_parser.destination_dir = tempdir
        ocw_parser.extract_foreign_media_locally()

    assert caplog.messages[0] == (
        "Could not fetch link http://ocw.mit.edu/ans7870/18/18.06/tools/Applets_sound/uropmovie.html "
        "for course 18-06-linear-algebra-spring-2010"
    )


def test_publish_date(ocw_parser):
    """Assert that we get first_published_to_production and last_published_to_production"""
    assert (
        ocw_parser.parsed_json["first_published_to_production"]
        == "2010/09/10 10:23:13.887 GMT-4"
    )
    assert (
        ocw_parser.parsed_json["last_published_to_production"]
        == "2019/09/25 17:47:34.670 Universal"
    )


@pytest.mark.parametrize(
    "field",
    [
        "first_published_to_production",
        "last_published_to_production",
        "last_unpublishing_date",
        "retirement_date",
    ],
)
def test_none(field):
    """Assert that "None" gets converted to a null value for certain fields"""
    with TemporaryDirectory() as destination_dir, TemporaryDirectory() as source_dir:
        course_dir = Path(source_dir) / "course-1"
        jsons_dir = course_dir / "0"
        shutil.copytree(
            "ocw_data_parser/test_json/course_dir/course-1/jsons", jsons_dir
        )
        with open(jsons_dir / "1.json") as file:
            json_1 = json.load(file)
        json_1[field] = "None"
        with open(jsons_dir / "1.json", "w") as file:
            json.dump(json_1, file)
        parser = OCWParser(
            course_dir=course_dir,
            destination_dir=destination_dir,
            static_prefix="static_files/",
        )
        assert parser.parsed_json[field] is None


def test_archived_course_fields(ocw_parser):
    """Assert that fields related to handling archived courses are passed through more or less"""
    assert ocw_parser.parsed_json["dspace_handle"] == ""
    assert ocw_parser.parsed_json["is_update_of"] == [
        "389a811a12a85b2225f41dca56699e0c"
    ]
    assert ocw_parser.parsed_json["features_tracking"] == [
        {
            "ocw_feature": "Translations",
            "ocw_feature_notes": "",
            "ocw_feature_url": "http://www.core.org.cn/OcwWeb/Mathematics/18-06Linear-AlgebraFall2002/CourseHome/index.htm",
            "ocw_speciality": "",
            "ocw_subfeature": "Chinese (Simplified)",
        },
        {
            "ocw_feature": "Translations",
            "ocw_feature_notes": "",
            "ocw_feature_url": "http://www.acikders.org.tr/course/view.php?id=32",
            "ocw_speciality": "",
            "ocw_subfeature": "Turkish",
        },
        {
            "ocw_feature": "Previous version",
            "ocw_feature_notes": "",
            "ocw_feature_url": "http://hdl.handle.net/1721.1/59010",
            "ocw_speciality": "",
            "ocw_subfeature": "",
        },
        {
            "ocw_feature": "Captions/Transcript",
            "ocw_feature_notes": "",
            "ocw_feature_url": "/courses/mathematics/18-06-linear-algebra-spring-2010/video-lectures",
            "ocw_speciality": "",
            "ocw_subfeature": "",
        },
    ]


@pytest.mark.parametrize("broken", [True, False])
def test_parse_ocw_feature_url(broken):
    """
    Test that ocw_feature_url links for Open Learning Library handles errors gracefully
    """
    with TemporaryDirectory() as destination_dir, TemporaryDirectory() as source_dir:
        shutil.copytree(
            "ocw_data_parser/test_json/course_dir/course-1",
            source_dir,
            dirs_exist_ok=True,
        )
        with open(Path(source_dir) / "jsons" / "1.json") as file:
            course_json = json.load(file)
        oll_feature = [
            feature
            for feature in course_json["courselist_features"]
            if feature["ocw_feature"] == "Open Learning Library"
        ][0]
        if broken:
            oll_feature["ocw_feature_url"] = "xyzzy"
        with open(Path(source_dir) / "jsons" / "1.json", "w") as file:
            json.dump(course_json, file)

        ocw_parser = OCWParser(
            course_dir=source_dir,
            destination_dir=destination_dir,
            static_prefix="static_files/",
        )
        parsed_json = ocw_parser.get_parsed_json()

        expected = (
            []
            if broken
            else [
                {
                    "course": "18.01.1x Calculus 1A Differentiation",
                    "url": "https://openlearninglibrary.mit.edu/courses/course-v1:MITx+18.01.1x+2T2019/about",
                },
                {
                    "course": "18.01.2x Calculus 1B Integration",
                    "url": "https://openlearninglibrary.mit.edu/courses/course-v1:MITx+18.01.2x+3T2019/about",
                },
                {
                    "course": "18.01.3x Calculus 1C Coordinate Systems & Infinite Series",
                    "url": "https://openlearninglibrary.mit.edu/courses/course-v1:MITx+18.01.3x+1T2020/about",
                },
            ]
        )
        assert parsed_json["open_learning_library_related"] == expected
