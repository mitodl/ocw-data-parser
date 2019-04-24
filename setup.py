import sys

from setuptools import setup, find_packages

if sys.version < "3.6":
    print("ERROR: python version 3 or higher is required")
    sys.exit(1)

setup(
    name="ocw_data_parser",
    version="0.2.5",
    packages=find_packages(),
    install_requires=["boto3>=1.9.62", "requests>=2.21.0", "smart-open>=1.8.0"],
    license="To be determined",
    author="Zagaran, Inc.",
    url="https://github.com/zagaran/ocw-data-parser",
    description="a parsing library for OpenCourseWare json exports",
)
