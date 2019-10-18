# ocw-data-parser

A parsing script for OCW course data. Additionally, you can use parsed output to generate static HTML site.

## Installation
This is a python 3.3+ project.

pip install the `ocw-data-parser` library:
```bash
pip install ocw-data-parser
```

## Usage
To parse OCW courses:

Place the raw Plone JSON files for each course in their own directory, and place those folders within another directory.  We will refer to this as the "course_dir."  You may place any number of courses in this directory.

```python
from ocw_data_parser import OCWParser

your_parser = OCWParser("path/to/course_dir/", "path/to/output/destination/")
your_parser.extract_media_locally()  # To extract the media files and master json locally inside output directory for each course directory in course_dir
your_parser.extract_foreign_media_locally()  # To extract media files hosted on the Akamai cloud

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
