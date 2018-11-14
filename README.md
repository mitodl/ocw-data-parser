# ocw-data-parser

A parsing script for OCW course data

## Installation
pip install the `ocw-data-parser` library:
```bash
pip install ocw-data-parser
```

## Usage
To parse a single OCW course:
```python
from ocw_data_parser import generate_output_for_course

generate_output_for_course(OCW_COURSE_DIR, DESTINATION_DIR)
```

To parse all your OCW data, you can run from bash:
```bash
python ocw_data_parser.py ROOT_DIR
```

or from python:
```python
from ocw_data_parser import ocw_parse_all

ocw_parse_all(OCW_DATA_DIR)
```
