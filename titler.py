#!/usr/bin/env python3
"""
process content files and create suitably formatted title tags
"""
import argparse
import os
import unicodedata
from enum import Enum
from bs4 import BeautifulSoup, Tag
import roman
import regex
from se.formatting import titlecase
from se.formatting import format_xhtml


class BookDivision(Enum):
	"""
	Enum to indicate the division of a particular ToC item.
	"""
	NONE = 0
	ARTICLE = 1
	SUBCHAPTER = 2
	CHAPTER = 3
	DIVISION = 4
	PART = 5
	VOLUME = 6


class TitleInfo:
	"""
	Object to hold information on a title
	"""
	title = ""  # this is for the heading title
	subtitle = ""  # this is for the heading subtitle if any
	cleaned_title = ""  # this is for the <title> tag, no embedded tags
	cleaned_subtitle = ""  # this is for the <title> tag, no embedded tags
	roman = ""
	number = 0
	division = BookDivision

	def output_title(self) -> str:
		"""
		:return: a suitably formatted and constructed string for a title tag
		"""
		if self.division == BookDivision.ARTICLE:
			prefix = ""
		elif self.division == BookDivision.CHAPTER:
			prefix = "Chapter"
		elif self.division == BookDivision.DIVISION:
			prefix = "Division"
		elif self.division == BookDivision.PART:
			prefix = "Part"
		elif self.division == BookDivision.VOLUME:
			prefix = "Volume"
		else:
			prefix = ""

		if self.subtitle:
			if prefix != "":
				return prefix + " " + str(self.number) + ": " + self.cleaned_subtitle
			else:
				if self.cleaned_title == "":
					return self.cleaned_subtitle
				else:
					return self.cleaned_title + ": " + self.cleaned_subtitle
		else:
			if prefix != "":
				if self.number > 0:
					return prefix + " " + str(self.number)
				else:
					return self.cleaned_title
			else:
				return self.cleaned_title

	def output_safe_id(self):
		return make_url_safe(self.cleaned_title + ": " + self.subtitle)


def make_url_safe(text: str) -> str:
	"""
	Return a URL-safe version of the input. For example, the string "Mother's Day" becomes "mothers-day".

	INPUTS
	text: A string to make URL-safe

	OUTPUTS
	A URL-safe version of the input string
	"""

	# 1. Convert accented characters to unaccented characters
	text = regex.sub(r"\p{M}", "", unicodedata.normalize("NFKD", text))

	# 2. Trim
	text = text.strip()

	# 3. Convert title to lowercase
	text = text.lower()

	# 4. Remove apostrophes
	text = regex.sub(r"['‘’]", "", text)

	# 4a. Remove double quotes
	text = regex.sub(r'["”“]', '', text)

	# 5. Convert any non-digit, non-letter character to a space
	text = regex.sub(r"[^0-9a-z]", " ", text, flags=regex.IGNORECASE)

	# 6. Convert any instance of one or more space to a dash
	text = regex.sub(r"\s+", "-", text)

	# 7. Remove trailing dashes
	text = regex.sub(r"\-+$", "", text)

	return text


def get_content_files(opf: BeautifulSoup) -> list:
	"""
	Reads the spine from content.opf to obtain a list of content files, in the order wanted for the ToC.
	"""
	itemrefs = opf.find_all("itemref")
	ret_list = []
	for itemref in itemrefs:
		ret_list.append(itemref["idref"])

	return ret_list


def gethtml(filename: str) -> str:
	"""
	reads an xhtml file and returns the text
	"""
	try:
		fileobject = open(filename, 'r', encoding='utf-8')
	except IOError:
		print('Could not open ' + filename)
		return ''
	text = fileobject.read()
	fileobject.close()
	return text


def puthtml(html: str, filename: str):
	"""
	Write out the new xhtml
	:param html: input html text
	:param filename: file to write to
	"""
	try:
		fileobject = open(filename, 'w', encoding='utf-8')
		fileobject.write(html)
	except IOError:
		print('Could not write to ' + filename)
		return
	fileobject.close()


def extract_contents_as_string(tag: Tag) -> str:
	"""
	Get text only from contents of tag
	:param tag: Beautiful Soup Tag
	:return: text of the tag
	"""
	accumulator = ""
	for content in tag.contents:
		accumulator += str(content)
	return accumulator


def process_first_heading(heading: BeautifulSoup) -> TitleInfo:
	"""
	Get title and subtitle text from heading
	:param heading: a soup object representing a heading
	:return: object containing title information
	"""
	title_info = TitleInfo()
	title_info.division = get_book_division(heading)

	spans = heading.find_all("span")
	if spans:
		for span in spans:
			epub_type = span.get("epub:type") or ""
			if "z3998:roman" in epub_type:
				title_info.roman = span.get_text()
				title_info.number = roman.fromRoman(title_info.roman)
			elif "subtitle" in epub_type:
				title_info.cleaned_subtitle = titlecase(span.get_text())
				title_info.subtitle = titlecase(extract_contents_as_string(span))
				sup = BeautifulSoup(title_info.subtitle, "html.parser")
				span.clear()
				span.append(sup)
			else:
				# no epub:type in span so must be simple title
				title_info.title = titlecase(extract_contents_as_string(span))
				title_info.cleaned_title = titlecase(span.get_text())
				sup = BeautifulSoup(title_info.title, "html.parser")
				span.clear()
				span.append(sup)
		return title_info
	else:  # no spans, probably simple title
		epub_type = heading.get("epub:type") or ""
		if "z3998:roman" in epub_type:
			# print(epub_type)
			title_info.roman = titlecase(heading.get_text())
			title_info.number = roman.fromRoman(title_info.roman)
		elif "title" in epub_type:
			# print(epub_type)
			title_info.title = titlecase(extract_contents_as_string(heading))
			title_info.cleaned_title = titlecase(heading.get_text())
			sup = BeautifulSoup(title_info.title, "html.parser")
			heading.clear()
			heading.append(sup)
		else:
			# what is in epub:type?
			print("Query: " + epub_type)
		return title_info


def process_file(filepath: str) -> (str, str):
	"""
	Run through each file, locating titles and updating <title> tag.

	INPUTS:
	filepath: path to content file

	OUTPUTS:
	altered xhtml file text and new section ID (as a tuple)
	"""
	xhtml = gethtml(filepath)
	soup = BeautifulSoup(xhtml, "html.parser")
	heading = soup.find(["h2", "h3", "h4", "h5", "h6"])  # find first heading, not interested in h1 in halftitle
	if heading:
		section = heading.find_parent("section")
		title_info = process_first_heading(heading)
		title_tag = soup.find("title")
		new_id = title_info.output_safe_id()
		if section:
			section["id"] = new_id
		if title_tag:
			title_tag.clear()
			title_tag.append(title_info.output_title())
			return format_xhtml(str(soup)), new_id
	return "", ""


def get_book_division(tag: BeautifulSoup) -> BookDivision:
	"""
	Determine and return the kind of book division.
	At present only Chapter, Part, Division and Volume are important;
	but others stored for possible future logic.
	"""
	parent_section = tag.find_parents(["section", "article"])
	if not parent_section:
		parent_section = tag.find_parents("body")
	section_epub_type = parent_section[0].get("epub:type") or ""
	if "part" in section_epub_type:
		return BookDivision.PART
	elif "division" in section_epub_type:
		return BookDivision.DIVISION
	elif ("volume" in section_epub_type) and ("se:short-story" not in section_epub_type):
		return BookDivision.VOLUME
	elif "subchapter" in section_epub_type:
		return BookDivision.SUBCHAPTER
	elif "chapter" in section_epub_type:
		return BookDivision.CHAPTER
	elif "article" in parent_section[0].name:
		return BookDivision.ARTICLE
	else:
		return BookDivision.NONE


# don't process these files
EXCLUDE_LIST = ["titlepage.xhtml", "colophon.xhtml", "uncopyright.xhtml", "imprint.xhtml", "halftitle.xhtml", "dedication.xhtml", "endnotes.xhtml", "loi.xhtml"]


def main():
	parser = argparse.ArgumentParser(description="Process titles and subtitles, set title case and update <title> tags.")
	parser.add_argument("-i", "--in_place", action="store_true", help="overwrite the existing xhtml files instead of printing to stdout")
	parser.add_argument("-r", "--rename", action="store_true", help="create xhtml files named for story titles")
	parser.add_argument("directory", metavar="DIRECTORY", help="a Standard Ebooks source directory")
	args = parser.parse_args()

	rootpath = args.directory
	opfpath = os.path.join(rootpath, 'src', 'epub', 'content.opf')
	textpath = os.path.join(rootpath, 'src', 'epub', 'text')

	if not os.path.exists(opfpath):
		print("Error: this does not seem to be a Standard Ebooks root directory")
		exit(-1)

	xhtml = gethtml(opfpath)
	soup = BeautifulSoup(xhtml, "lxml")
	file_list = get_content_files(soup)
	processed = 0
	for file_name in file_list:
		if file_name in EXCLUDE_LIST:  # ignore it
			continue
		result = process_file(os.path.join(textpath, file_name))
		if result[0] != "":
			out_xhtml = result[0]
			processed += 1
			if args.in_place:
				puthtml(out_xhtml, os.path.join(textpath, file_name))
			elif args.rename and result[1] != "":
				renamed_fname = result[1] + ".xhtml"
				puthtml(out_xhtml, os.path.join(textpath, renamed_fname))
			else:
				print(out_xhtml)
	if processed == 0:
		print("No files processed. Did you update manifest and order the spine?")


if __name__ == "__main__":
	main()