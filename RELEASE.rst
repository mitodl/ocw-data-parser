Release Notes
=============

Version 0.28.0 (Released April 29, 2021)
--------------

- parse aka_course_number into new_course_numbers (#140)

Version 0.27.0 (Released April 23, 2021)
--------------

- update course features

Version 0.26.0 (Released March 29, 2021)
--------------

- Fix: typo "Simulation Vidoes" (#134)

Version 0.25.0 (Released March 15, 2021)
--------------

- add template_type to course_embedded_media (#132)

Version 0.24.0 (Released March 03, 2021)
--------------

- fix a typo with 'exams with solutions' (#128)

Version 0.23.0 (Released February 17, 2021)
--------------

- course feature tags (#126)

Version 0.22.0 (Released January 19, 2021)
--------------

- Handle "None" values for certain fields (#121)

Version 0.21.1 (Released January 13, 2021)
--------------

- handle divided instructor insights sections (#119)
- Fetch missing media files (#113)

Version 0.21.0 (Released January 12, 2021)
--------------

- add SRHomePage to the types of pages that are parsed (#117)
- Check for errors when downloading media (#106)

Version 0.20.0 (Released December 22, 2020)
--------------

- accept `text/plain` format for course pages, and update tests to reflect that (#114)

Version 0.19.0 (Released December 09, 2020)
--------------

- fix file_location bug (#104)
- Fix media_uid_filter argument (#105)
- Add black and pylint and run them in github actions (#99)
- Switch to github actions (#98)
- Refactor to use pathlib (#96)
- Turn off codecov checks (#87)

Version 0.18.0 (Released November 24, 2020)
--------------

- fix upload_parsed_json argument in parse_all (#94)

Version 0.17.0 (Released November 19, 2020)
--------------

- Fix null instructors error (#90)
- Fix load_raw_jsons sorting (#91)

Version 0.16.0 (Released November 10, 2020)
--------------

- fix test (#88)
- Download S3 files to original full path and adjust parse_all to find them (#82)
- add master_subject array to master json (#74)

Version 0.15.1 (Released November 06, 2020)
--------------

- Add first_published_to_production (#84)
- refactor master -> parsed and change output file name (#78)

Version 0.15.0 (Released November 05, 2020)
--------------

- Add option to upload master json to s3 in parse_all function (#77)

Version 0.14.1 (Released October 30, 2020)
--------------

- Strip whitespace from external links (#73)
- Various refactoring (#66)

Version 0.14.0 (Released October 27, 2020)
--------------

- improve file parser error messages

Version 0.13.0 (Released October 23, 2020)
--------------

- Add some tests to assert that refactoring worked (#68)
- Add open_learning_library_related (#54)
- Provide an empty list if there are no instructors (#64)
- Include bottomtext section in parsed JSON (#63)
- Remove static html generator since we are replacing it with hugo-course-publisher (#58)
- Fix loaded_jsons initialization (#59)
- Add PR template (#60)
- Remove safe_get (#62)

Version 0.12.0 (Released October 13, 2020)
--------------

- publishing dates (#51)

Version 0.11.0 (Released September 11, 2020)
--------------

- fix file_location in parsed json uploaded by upload_course_image (#48)

Version 0.10.0 (Released July 21, 2020)
--------------

- add short_page_title to pages (#44)
- fix course downloader (#43)
- add list_in_left_nav (#41)
- add other_information_text to parsed json (#40)

Version 0.9.0 (Released July 08, 2020)
-------------

- S3 Download functionality & local parse workflow (#38)

Version 0.8.0 (Released June 26, 2020)
-------------

- Add order_index (#36)
- add SupplementalResourceSection to the types of pages scanned (#35)
- add some tests for file generation functions (#19)

Version 0.7.0 (Released June 08, 2020)
-------------

- add is_image_gallery to parsed json course_pages objects (#33)

Version 0.6.0 (Released March 31, 2020)
-------------

- upload parsed json in image only s3 upload

Version 0.5.0 (Released March 23, 2020)
-------------

- add thumbnail image to parsed json

Version 0.4.0 (Released March 16, 2020)
-------------

- remove missing thumbnail error

Version 0.3.0 (Released February 12, 2020)
-------------

- Write raw HTML for course pages (#25)
- Add unit tests (#20)
- Media gallery support (#16)
- Fix course image caption and alt text, course features links (#15)
- Add optional static prefix (#14)
- Remove travis config from master
- Pushing basic travis config to master because travis doesn't like you to be able to select another branch to test it first...
- Corrected a misunderstanding about how the parser works
- Update README commands (#11)

