# -*- coding: utf-8 -*-
#
# Copyright © 2015,2016 Mathieu Duponchelle <mathieu.duponchelle@opencreed.com>
# Copyright © 2015,2016 Collabora Ltd
#
# This library is free software; you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; either version 2.1 of the License, or (at your option)
# any later version.
#
# This library is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library.  If not, see <http://www.gnu.org/licenses/>.

# pylint: disable=missing-docstring

import re
import os
import shutil
import json
import glob
import io

from collections import defaultdict

from lxml import etree
import lxml.html

from hotdoc.core.exceptions import InvalidOutputException
from hotdoc.utils.loggable import info as core_info, Logger

from hotdoc.extensions.search.trie import Trie
from hotdoc.utils.utils import OrderedSet


def info(message):
    core_info(message, domain='search-extension')

Logger.register_warning_code('invalid-html', InvalidOutputException,
                             'search-extension')

SECTIONS_SELECTOR = (
    './div[@id]'
)

INITIAL_SELECTOR = (
    './/div[@id="main"]'
)

TITLE_SELECTOR = (
    './ul[@class="base_symbol_header"]'
    '/li'
    '/h3'
    '/span'
    '/code'
)

TOK_REGEX = re.compile(r'[a-zA-Z_][a-zA-Z0-9_\.]*[a-zA-Z0-9_]')


def get_sections(root, selector='./div[@id]'):
    return root.xpath(selector)


def parse_content(section, stop_words, selector='.//p'):
    for elem in section.xpath(selector):
        text = lxml.html.tostring(elem, method="text",
                                  encoding='unicode')

        tokens = TOK_REGEX.findall(text)

        for token in tokens:
            original_token = token + ' '
            if token in stop_words:
                yield (None, original_token)
                continue

            yield (token, original_token)

        yield (None, '\n')


def write_fragment(fragments_dir, url, text):
    dest = os.path.join(fragments_dir, url + '.fragment')
    dest = dest.replace('#', '-')
    try:
        _ = open(dest, 'w')
    except IOError:
        os.makedirs(os.path.dirname(dest))
        _ = open(dest, 'w')
    finally:
        _.write("fragment_downloaded_cb(")
        _.write(json.dumps({"url": url, "fragment": text}))
        _.write(");")
        _.close()


def parse_file(root_dir, filename, stop_words, fragments_dir):
    with io.open(filename, 'r', encoding='utf-8') as _:
        contents = _.read()
    root = etree.HTML(contents)

    if root.attrib.get('id') == 'main':
        initial = root
    else:
        initial = root.xpath(INITIAL_SELECTOR)

        if not len(initial):
            return

        initial = initial[0]

    url = os.path.relpath(filename, root_dir)

    sections = get_sections(initial, SECTIONS_SELECTOR)
    for section in sections:
        section_url = '%s#%s' % (url, section.attrib.get('id', '').strip())
        section_text = ''

        for tok, text in parse_content(section, stop_words,
                                       selector=TITLE_SELECTOR):
            section_text += text
            if tok is None:
                continue
            yield tok, section_url, True
            if any(c.isupper() for c in tok):
                yield tok.lower(), section_url, True

        for tok, text in parse_content(section, stop_words):
            section_text += text
            if tok is None:
                continue
            yield tok, section_url, False
            if any(c.isupper() for c in tok):
                yield tok.lower(), section_url, False

        write_fragment(fragments_dir,
                       section_url,
                       lxml.html.tostring(section, encoding='unicode'))


def prepare_folder(dest):
    if os.path.isdir(dest):
        return

    try:
        shutil.rmtree(dest)
    except OSError:
        pass

    try:
        os.mkdir(dest)
    except OSError:
        pass


class SearchIndex(object):

    def __init__(self, scan_dir, output_dir, private_dir):
        self.__scan_dir = scan_dir
        self.__output_dir = output_dir
        self.__private_dir = private_dir

        prepare_folder(self.__search_dir)
        prepare_folder(self.__fragments_dir)

        self.__full_index = defaultdict(list)
        self.__new_index = defaultdict(list)
        self.__trie = Trie()

    def scan(self, stale_filenames):
        self.load(stale_filenames)
        self.fill(stale_filenames)
        self.save()

    @property
    def __search_dir(self):
        return os.path.join(self.__output_dir, 'search')

    @property
    def __fragments_dir(self):
        return os.path.join(self.__search_dir, 'hotdoc_fragments')

    def __get_fragments(self, filenames):
        fragments = set()

        for filename in filenames:
            url = os.path.relpath(filename, self.__scan_dir)
            for fragment in glob.glob(
                    os.path.join(self.__fragments_dir, url) + '*'):
                fragments.add(os.path.relpath(fragment,
                                              self.__fragments_dir)[:-9])
                os.unlink(fragment)

        return fragments

    def load(self, stale_filenames):
        to_remove = self.__get_fragments(stale_filenames)

        trie_path = os.path.join(self.__private_dir, 'search.trie')
        if os.path.exists(trie_path):
            self.__trie = Trie.from_file(trie_path)

        search_index_path = os.path.join(self.__private_dir, 'search.json')
        if os.path.exists(search_index_path):
            with open(search_index_path, 'r') as _:
                previous_index = json.loads(_.read())

            for token, fragment_urls in list(previous_index.items()):
                new_set = list(OrderedSet(fragment_urls) - to_remove)

                if new_set:
                    self.__full_index[token] = new_set
                else:
                    self.__trie.remove(token)
                    os.unlink(os.path.join(self.__search_dir, token))

    def fill(self, filenames):
        here = os.path.dirname(__file__)
        with open(os.path.join(here, 'stopwords.txt'), 'r') as _:
            stop_words = set(_.read().split())

        for filename in filenames:
            if not os.path.exists(filename):
                continue

            for token, section_url, prioritize in parse_file(
                    self.__scan_dir,
                    filename,
                    stop_words,
                    self.__fragments_dir):
                if not prioritize:
                    self.__full_index[token].append(section_url)
                    self.__new_index[token].append(section_url)
                else:
                    self.__full_index[token].insert(0, section_url)
                    self.__new_index[token].insert(0, section_url)

    def save(self):
        for key, value in sorted(self.__new_index.items()):
            self.__trie.insert(key)

            metadata = {'token': key, 'urls': list(OrderedSet(value))}

            with open(os.path.join(self.__search_dir, key), 'w') as _:
                _.write("urls_downloaded_cb(")
                _.write(json.dumps(metadata))
                _.write(");")

        self.__trie.to_file(os.path.join(self.__private_dir, 'search.trie'),
                            os.path.join(self.__output_dir, 'trie_index.js'))

        with open(os.path.join(self.__private_dir, 'search.json'), 'w') as _:
            _.write(json.dumps(self.__full_index))
