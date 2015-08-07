#!/usr/bin/python
# -*- Mode: Python -*-
# Copyright (C) 2015 Mathieu Duponchelle
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.
#

import os
import sys
import __builtin__

if os.name == 'nt':
    datadir = os.path.join(os.path.dirname(__file__), '..', 'share')
else:
    datadir = "/usr/share"

__builtin__.__dict__['DATADIR'] = datadir

srcdir = os.getenv('UNINSTALLED_INTROSPECTION_SRCDIR', None)
if srcdir is not None:
    path = srcdir
else:
    # This is a private directory, we don't want to pollute the global
    # namespace.
    if os.name == 'nt':
        # Makes g-ir-doc-tool 'relocatable' at runtime on Windows.
        path = os.path.join(os.path.dirname(__file__), '..', 'lib', 'gobject-introspection')
    else:
        path = os.path.join('/usr/lib64', 'gobject-introspection')
sys.path.insert(0, path)

sys.path = [p for p in sys.path if not "python3" in p]

dir_ = os.path.dirname(os.path.abspath(__file__))
sys.path.append(dir_)

from core.main import main

sys.exit(main(sys.argv))