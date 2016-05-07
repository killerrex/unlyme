#!/usr/bin/env python3

"""
Copyright 2016 A. Ayala

This file is part of Unlyme.

Unlyme is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Unlyme is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Unlyme.  If not, see <http://www.gnu.org/licenses/>.

"""

import sys
import argparse

from lymefile import LymeFile

desc = "Lyme file extractor"
epilog = "The new format was found in some Broadcom drivers"

parser = argparse.ArgumentParser(description=desc, epilog=epilog)

parser.add_argument(
    '-f', '--format', choices=['new', 'old'], default='new',
    help="Select the input file format (Default %(default)s)"
)

parser.add_argument(
    '-b', '--endian', choices=['auto', 'big', 'little'], default='auto',
    help="How the offsets and sizes are coded (Default %(default)s)"
)

parser.add_argument(
    '-p', '--posix', action='store_true',
    help="Use POSIX paths in the listing instead of windows paths"
)

g = parser.add_mutually_exclusive_group()
g.add_argument(
    '-a', '--action', choices=['list', 'extract'], default='list',
    help='Decide between extract the files or just list the contents (default)'
)
g.add_argument(
    '-e', '--extract', action='store_const', dest='action', const='extract',
    help='Extract the contents of the Lyme file'
)
g.add_argument(
    '-l', '--list', action='store_const', dest='action', const='list',
    help='List the contents of the Lyme file'
)

parser.add_argument(
    '-o', '--output', dest='output', default='.',
    help='Directory to extract the data (default %(default)s)'
)

parser.add_argument(
    'lyme', nargs='?', type=argparse.FileType('rb'),
    default=sys.stdin, help='Input file'
)

args = parser.parse_args()

# Prepare the general options and read the input file
endian_mode = {'auto': None, 'big': '>', 'little': '<'}

endian = endian_mode[args.endian]
old = args.format == 'old'

ly = LymeFile(args.lyme, old, endian)

if args.action == 'list':
    ly.list(args.posix)
elif args.action == 'extract':
    ly.extractall(args.output)
else:
    print('Unexpected action {}'.format(args.action))
