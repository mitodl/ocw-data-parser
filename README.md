# ocw-data-parser

A parsing script for OCW course data. Additionally, you can use parsed output to generate static HTML site.

## Installation
This is a python 3.3+ project.

pip install the `ocw-data-parser` library:
```bash
pip install ocw-data-parser
```

## Usage
Each OCW course exported from Plone usually has a single folder named "0" under the course directory.  This directory structure must be maintained for the parser to work correctly.  When "course_dir" is referred to here, we are talking about the directory that contains this "0" directory.

To parse a single OCW course:

```python
from ocw_data_parser import OCWParser

your_parser = OCWParser("path/to/course_dir/", "path/to/output/destination/")
# Extract the media files and master json locally inside output directory for each course directory in course_dir
your_parser.extract_media_locally()
# Extract media files hosted on the Akamai cloud
your_parser.extract_foreign_media_locally()

# To upload all media to your S3 Bucket
# First make sure your AWS credentials are setup in your local environment
# Second, setup your s3 info
your_parser.setup_s3_uploading("your_bucket_name", "optional_containing_folder")
# Then, call upload all media to s3
your_parser.upload_all_media_to_s3()
# To upload course image thumbnail only
your_parser.upload_course_image()
```

To generate static HTML site for OCW course:

```python
from ocw_data_parser import generate_html_for_course

generate_html_for_course("path/to/master.json", "path/to/output/destination/")
```

## Local Workflow

To download a list of courses based on `example_courses.json`, placed in `private` as `courses.json`:

```python
from course_downloader import OCWDownloader

downloader = OCWDownloader("private/courses.json", "PROD", "private/raw_courses", "ocw-content-storage")
downloader.downloadCourses()
```
In order for the above to work, you need `awscli` installed on your machine and it needs to be configured for access to the bucket that you specify.

To parse a folder of course folders (like the ones downloaded above) and export only master json with s3 links:

```python
from util import parse_all

parse_all(coursesDir="private/raw_courses", destinationDir="../ocw-to-hugo/private/courses", s3Bucket="open-learning-course-data-ci", s3Links=True, overwrite=True, beautifyMasterJson=True)
```