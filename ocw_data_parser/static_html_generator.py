import logging
import os
from ocw_data_parser.utils import is_json, get_correct_path, load_json_file

log = logging.getLogger(__name__)


def generate_html_for_course(master_json, destination):
    if not is_json(master_json):
        return
    loaded_master_json = load_json_file(master_json)
    destination = get_correct_path(destination)
    
    # Check if course files are exported locally or uploaded to S3
    for m in loaded_master_json["course_files"]:
        if "file_location" not in m:
            log.error("Please make sure to export media locally or upload to S3 before trying to generate HTML site")
            return
    
    # Create linked pages
    generate_linked_pages(loaded_master_json["course_pages"], destination, loaded_master_json)
    # Create the course index page
    generate_index_page(loaded_master_json, destination)
    log.info("Static website has been generated for %s and be found at: %s",loaded_master_json["title"], destination)


def generate_index_page(mj, destination):
    os.makedirs(destination, exist_ok=True)
    destination = get_correct_path(destination) + "index.html"
    with open(destination, "w") as f:
        # Order of these f writes is important
        f.write(generate_header_and_start_body(mj))
        f.write(generate_breadcrumbs(mj, mj["uid"]))
        f.write(generate_course_container(mj))
        f.write(generate_side_menu(mj))
        f.write(generate_main_content(mj))
        f.write("</body>\n</html>\n")


def generate_header_and_start_body(mj):
    s = "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n<title>%s</title>\n<link rel=\"stylesheet\" href=\"https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css\" integrity=\"sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T\" crossorigin=\"anonymous\"><script src=\"https://code.jquery.com/jquery-3.3.1.slim.min.js\" integrity=\"sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo\" crossorigin=\"anonymous\"></script><script src=\"https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.14.7/umd/popper.min.js\" integrity=\"sha384-UO2eT0CpHqdSJQ6hJty5KVphtPhzWj9WO1clHTMGa3JDZwrnQq4sF86dIHNDz0W1\" crossorigin=\"anonymous\"></script><script src=\"https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/js/bootstrap.min.js\" integrity=\"sha384-JjSmVgyd0p3pXB1rRibZUAYoIIy6OrQ6VrjIEaFf/nJGzIxFDsf4x0xIM+B07jRM\" crossorigin=\"anonymous\"></script>\n</head>\n<body style=\"background-color: floralwhite\">\n" \
        % mj["title"]
    return s


def generate_breadcrumbs(mj, current_page_uid):
    s = "<nav><ol class=\"breadcrumb\">\n%s</ol>\n</nav>\n"
    page_trail = list()
    embedded_media = None
    # Find out if we are viewing some embedded media
    if "course_embedded_media" in mj:
        for inline_embed_id in mj['course_embedded_media']:
            media = mj['course_embedded_media'][inline_embed_id]
            if current_page_uid == media["uid"]:
                embedded_media = media
    # Find which page we are on
    for page in mj["course_pages"]:
        if page["uid"] == current_page_uid:
            page_trail.append(page)
            break
        elif embedded_media:
            if page["uid"] == embedded_media["parent_uid"]:
                page_trail.append(page)
                page_trail.append(embedded_media)
                break
    # If page_trail is empty that means we're generating breadcrumbs for the home page
    if not page_trail:
        breadcrumbs = "<li class=\"breadcrumb-item active\"><a href=\"index.html\">%s</a></li>\n" % mj["title"]
    else:
        prefix = (len(page_trail) - 1) * '../'
        breadcrumbs = "<li class=\"breadcrumb-item\"><a href=\"%sindex.html\">%s</a></li>\n" % (prefix, mj["title"])
        for item in page_trail[:-1]:
            prefix = (page_trail.index(item) + 1) * '../'
            breadcrumbs += "<li class=\"breadcrumb-item\"><a href=\"%s%s\">%s</a></li>\n" % (
            prefix, compose_page_name(item), item["title"])
        breadcrumbs += "<li class=\"breadcrumb-item active\"><a href=\"%s\">%s</a></li>\n" % (
            compose_page_name(page_trail[-1]), page_trail[-1]["title"])
    return s % breadcrumbs


def generate_course_container(mj):
    return "<div class=\"container\">\n<h1>%s</h1>\n<hr />\n" % mj["title"]


def generate_side_menu(mj, prefix=""):
    main_navs = list()
    rest_of_pages = list()
    for page in mj["course_pages"]:
        if page["parent_uid"] == mj["uid"]:
            main_navs.append(page)
        else:
            rest_of_pages.append(page)
    s = "<div class=\"course-content row\">\n<div class=\"side-menu col-3\">\n<ul>\n"
    for page in main_navs:
        s += "<li><a href=\"%s\">%s</a>" % (prefix + (compose_page_name(page)), page["title"])
        sub_pages = get_sub_pages(rest_of_pages, page["uid"])
        if sub_pages:
            s += "<ul>\n"
            for sp in sub_pages:
                s += "<li><a href=\"%s\">%s</a></li>\n" % (prefix + (compose_page_name(sp)), sp["title"])
            s += "</ul>\n"
        s += "</li>\n"
    s += "</ul>\n</div>\n"
    return s


def generate_main_content(mj):
    s = "<div class=\"main-content col-9\">\n"
    # generate content here
    s += get_course_thumbnail(mj)
    s += get_course_info(mj)
    s += "<div class=\"clearfix\"></div>"
    s += get_course_features(mj)
    s += get_course_description(mj)
    s += get_course_collections(mj)
    s += "</div>\n</div>\n</div>\n"
    return s


def get_course_thumbnail(mj):
    cn_peices = mj["short_url"].split("-")
    thumbnail_name = cn_peices[0] + "-" + cn_peices[1] + cn_peices[-2][0] + cn_peices[-1][2:] + ".jpg"
    for media in mj["course_files"]:
        if media["parent_uid"] == mj["uid"]:
            thumbnail_name = media["uid"] + "_" + thumbnail_name
            if media["file_location"].split("/")[-1] == thumbnail_name:
                return "<div class=\"container\"><div class=\"card float-left\" style=\"max-width: 330px;\"><img class=\"card-img-top\" alt=\"%s\" src=\"%s\" title=\"%s\" />\n<div class=\"card-body\"><p class=\"card-text\">\n%s\n</p></div></div>" % \
                       (mj["image_alternate_text"], media["file_location"], mj["image_alternate_text"], mj["image_caption_text"])
    return ""


def get_course_info(mj):
    instructors_str = ""
    for instructor in mj["instructors"]:
        instructors_str += "<li>%s %s</li>\n" % (instructor["first_name"], instructor["last_name"])
    course_number = "%s" % (mj["sort_as"])
    if mj["extra_course_number"]:
        course_number += " / %s" % mj["extra_course_number"][0]["sort_as_col"]
    taught_in = "%s %s" % (mj["from_semester"], mj["from_year"])
    level = mj["course_level"]
    info_str = "<div class=\"float-right\"><ul><li><h4>Instructor(s)</h4>\n<ul>%s</ul></li><li><h4>MIT Course Number: </h4>%s</li><li><h4>As Taught In: </h4>%s</li><li><h4>Level: </h4>%s</li></ul></div></div>" % (
    instructors_str, course_number, taught_in, level)
    return info_str


def get_course_features(mj):
    course_features = "<h4>Course Features</h4>\n<ul>%s</ul>\n"
    features = ""
    if mj["course_features"]:
        for entry in mj["course_features"]:
            features += fix_links("<li><a href=\"%s\">%s</a></li>\n" % (entry["ocw_feature_url"], entry["ocw_feature"]), mj)
    return course_features % features


def get_course_description(mj):
    return "<h4>Course Description</h4>\n<p>%s</p>\n" % mj["description"]


def get_course_collections(mj):
    course_collections = "<hr />\n<h4>Course Collections</h4>\n<p>See related courses in the following collections:</p>\n<p>Find Courses by Topic</p>\n<ul>%s</ul>\n"
    list_of_collections = ""
    if mj["course_collections"]:
        for entry in mj["course_collections"]:
            feature = entry.get("ocw_feature", "")
            subfeature = entry.get("ocw_subfeature", "")
            speciality = entry.get("ocw_speciality", "")
            if speciality:
                subfeature += " >"
            if subfeature:
                feature += " >"
            list_of_collections += "<li><a href=\"#\">%s  %s  %s</a></li>\n" % (feature, subfeature, speciality)
    return course_collections % list_of_collections


def compose_page_name(page):
    page_name = page["short_url"]
    if page_name == "index.htm":
        page_name = "index"
    return page_name + ".html"


def generate_linked_pages(linked_pages, destination, mj):
    destination = get_correct_path(destination)
    for page in linked_pages:
        if page["url"] and not page["url"].split("/")[-1] == "index.htm":
            os.makedirs(destination, exist_ok=True)
            with open(destination + compose_page_name(page), "w") as f:
                f.write(generate_header_and_start_body(page))
                f.write(generate_breadcrumbs(mj, page["uid"]))
                f.write(generate_course_container(page))
                f.write(generate_side_menu(mj))
                f.write("<div class=\"main-content col-9\">\n")
                if page["text"]:
                    f.write(fix_links(page["text"], mj))
                if "course_embedded_media" in mj and page["is_media_gallery"]:
                    generate_embedded_media_pages(page, destination, mj)
                    f.write(generate_embedded_media_playlist(page, destination, mj))
                f.write("</div>\n</div>\n</div>\n")

def generate_embedded_media_pages(page, destination, mj):
    course_embedded_media = mj["course_embedded_media"]
    for inline_embed_id in course_embedded_media:
        embedded_media = course_embedded_media[inline_embed_id]
        # make sure the embedded media belongs to this page
        if embedded_media["parent_uid"] == page["uid"]:
            generate_embedded_media_page(page, embedded_media, destination, mj)

def generate_embedded_media_playlist(page, destination, mj, prefix=""):
    embedded_media_playlist_html = "<ul id=\"embedded_media\">"
    course_embedded_media = mj["course_embedded_media"]
    for inline_embed_id in course_embedded_media:
        embedded_media = course_embedded_media[inline_embed_id]
        # make sure the embedded media belongs to this page
        if embedded_media["parent_uid"] == page["uid"]:
            # generate the embedded media links
            page_url = prefix + compose_page_name(page).replace('.html', '') + '/' + embedded_media["short_url"] + '.html'
            thumbnail_url = ''
            for media in embedded_media["embedded_media"]:
                if media["type"] == "Thumbnail" and "media_location" in media:
                    thumbnail_url = media["media_location"]
            embedded_media_playlist_html += "<li id=\"" + embedded_media["inline_embed_id"] + "\">"
            embedded_media_playlist_html += "<a href=\"" + page_url + "\">"
            embedded_media_playlist_html += "<img src=\"" + thumbnail_url + "\">"
            embedded_media_playlist_html += "<span>" + embedded_media["title"] + "</span>"
            embedded_media_playlist_html += "</a>"
            embedded_media_playlist_html += "</li>"
    embedded_media_playlist_html += "</ul>"
    return embedded_media_playlist_html

def generate_embedded_media_page(page, embedded_media, destination, mj):
    directory = get_correct_path(destination) + compose_page_name(page).replace('.html', '') + '/'
    os.makedirs(directory, exist_ok=True)
    destination = directory + embedded_media["short_url"] + '.html'
    youtube_id = ''
    with open(destination, "w") as f:
        f.write(generate_header_and_start_body(embedded_media))
        f.write(generate_breadcrumbs(mj, embedded_media["uid"]))
        f.write(generate_course_container(embedded_media))
        f.write(generate_side_menu(mj, prefix="../"))
        f.write("<div class=\"main-content col-9\">\n")
        f.write(get_youtube_embedded_html(embedded_media))
        f.write("<ul class=\"nav nav-tabs\">\n")
        f.write("<li class=\"nav-item\"><a href=\"#about\" class=\"nav-link active\" data-toggle=\"tab\">About this Video</a></li>\n")
        f.write("<li class=\"nav-item\"><a href=\"#playlist\" class=\"nav-link\" data-toggle=\"tab\">Playlist</a></li>\n")
        f.write("<li class=\"nav-item\"><a href=\"#related-resources\" class=\"nav-link\" data-toggle=\"tab\">Related Resources</a></li>\n")
        f.write("<li class=\"nav-item\"><a href=\"#transcript\" class=\"nav-link\" data-toggle=\"tab\">Transcript</a></li>\n")
        f.write("<li class=\"nav-item\"><a href=\"#download\" class=\"nav-link\" data-toggle=\"tab\">Download this Video</a></li>\n")
        f.write("</ul>\n")
        f.write("<div class=\"tab-content\">\n")
        f.write("<div class=\"tab-pane fade show active\" id=\"about\">\n")
        f.write(embedded_media["about_this_resource_text"] + "\n")
        f.write("</div>\n")
        f.write("<div class=\"tab-pane fade\" id=\"playlist\">\n")
        f.write(generate_embedded_media_playlist(page, destination, mj, prefix="../"))
        f.write("</div>\n")
        f.write("<div class=\"tab-pane fade\" id=\"related-resources\">\n")
        f.write(fix_links(embedded_media["related_resources_text"], mj, prefix="../") + "\n")
        f.write("</div>\n")
        f.write("<div class=\"tab-pane fade\" id=\"transcript\">\n")
        f.write(embedded_media["transcript"])
        f.write("</div>\n")
        f.write("<div class=\"tab-pane fade\" id=\"download\">\n")
        f.write(get_video_download_html(embedded_media))
        f.write("</div>\n")
        f.write("</div>\n")
        f.write("</div>\n</div>\n</div>\n")
    return compose_page_name(page).replace('.html', '') + '/' + embedded_media["short_url"] + '.html'

def get_sub_pages(linked_pages, page_uid):
    return_arr = list()
    for page in linked_pages:
        if page["parent_uid"] == page_uid:
            return_arr.append(page)
    return return_arr


def get_media_related_to_page(linked_media, page_uid):
    """
    Returns a list of media files that exist inside the passed page

    linked_media: full list of linked_media
    page_uid: uid of the media containing page
    """
    return_arr = list()
    for media in linked_media:
        if media["parent_uid"] == page_uid:
            return_arr.append(media)
    return return_arr


def get_youtube_embedded_html(obj):
    s = ""
    for media in obj["embedded_media"]:
        if media["id"] == "Video-YouTube-Stream":
            s += "<div class=\"text-center\"><iframe width=\"560\" height=\"315\" src=\"https://www.youtube-nocookie.com/embed/%s\" frameborder=\"0\" allow=\"encrypted-media; picture-in-picture\"></iframe></div>" % \
                 media["media_location"]
    return s

def get_video_download_html(obj):
    s = ""
    for media in obj["embedded_media"]:
        if media["id"] == "Video-iTunesU-MP4":
            s += "<p><a href=\"%s\">Download from iTunes</a></p>" % media["media_location"]
        elif media["id"] == "Video-InternetArchive-MP4":
            s += "<p><a href=\"%s\">Download from Internet Archive</a></p>" % media["media_location"]
        elif ".srt" in media["id"] or ".pdf" in media["id"]:
            s += "<p><a href=\"../static_files/%s_%s\">Download caption file</a></p>" % (media["uid"], media["id"])
    return s

def fix_links(html_str, mj, prefix=""):
    # Fix links to linked pages
    for page in mj["course_pages"]:
        placeholder = "resolveuid/" + page["uid"]
        if placeholder in html_str:
            html_str = html_str.replace(placeholder, prefix + compose_page_name(page))
    # Fix links to linked media
    for media in mj["course_files"]:
        placeholder = "resolveuid/" + media["uid"]
        if placeholder in html_str:
            media_path = media["file_location"]
            html_str = html_str.replace(placeholder, prefix + media_path)
    # Fix embedded media
    if "course_embedded_media" in mj:
        for key, val in mj["course_embedded_media"].items():
            if key in html_str:
                s = get_youtube_embedded_html(val)
                html_str = html_str.replace(key, s)
    return html_str
