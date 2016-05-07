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


import os
import io
import struct
import pathlib
import zlib
import warnings


class LymeError(Exception):
    pass


class LymeInfo:
    """
    Information about an entry in a Lyme file

    Attributes:
        path: A PureWindowsPath with the name of the file or directory
        is_dir: Flag to mark the entry as a folder
        offset: Byte offset from the start of the Lyme File.
        length: Byte length of the original file
        size: Byte length of the compressed data

    Note:
        The offset is the value in the creation time, for this reason
        it can have a misalignment with the value returned by tell().
        the LymeFile tries to correct this using a bias during the extraction.
    """

    @classmethod
    def from_fd(cls, fd, old, endian='>'):
        """
        Read the description from the current position in the file

        Notice that this method shall only be used from LymeFile
        The fd final state will be at the beginning of the next element.

        The structure goes backwards from the end of the file with:
        Bytes          Type  Content
            4  unsigned int   offset
            4  unsigned int   length
            4  unsigned int     size
            n          char     path
            4  unsigned int        n
            1          bool   is_dir

        For old formats, the is_dir entry does not exist. the criteria for
        folders in that case is that both offset and size are 0

        Args:
            fd: A file descriptor
            old: flag to use the old format
            endian: One of > or < for little or big endian coding

        Returns:
            A new LymeInfo object

        """
        assert(isinstance(fd, io.BufferedIOBase))

        # First bytes: length of the path and directory flag
        if old:
            ini = 4
            fd.seek(-ini, io.SEEK_CUR)
            raw = fd.read(ini)
            n, = struct.unpack(endian + 'I', raw)
            flag = None
        else:
            ini = 5
            fd.seek(-ini, io.SEEK_CUR)
            raw = fd.read(ini)
            n, flag = struct.unpack(endian + 'Ib', raw)

        # Now go back the full record: offset + length + size + name
        fd.seek(-(ini + n + 3*4), io.SEEK_CUR)

        # Read only the 3 bytes of the file position and the name
        raw = fd.read(3*4 + n)
        offset, length, size = struct.unpack(endian + 'III', raw[:12])
        # TODO: It is enough here using the decode with UTF-8?
        path = raw[12:].decode()

        # Go back to the start of this record
        fd.seek(-len(raw), io.SEEK_CUR)

        if old:
            # Determine the directory flag
            is_dir = offset == 0 and size == 0
        else:
            is_dir = flag == 1

        return cls(path, is_dir, offset, length, size)

    def __init__(self, path, is_dir, offset, length, size):
        """
        Create a new description for a Lyme file

        Args:
            path: Full windows path
            is_dir: Flag to identify the directories
            offset: Initial position in the file
            length: Byte length of the file once expanded
            size: Byte length of the compressed data
        """
        super().__init__()

        self.path = pathlib.PureWindowsPath(path)
        self.is_dir = is_dir
        self.offset = offset
        self.length = length
        self.size = size

    def __repr__(self):
        return "{}({}, {}, {}, {}, {})".format(
            type(self).__name__, self.path, self.is_dir,
            self.offset, self.length, self.size
        )

    def write(self, fd, bias, out, step=None):
        """
        Extract from fd and write to out
        Args:
            fd: File descriptor to read
            bias: error in the file position information
            out: File descriptor to write
            step: Maximum bytes to read each time. None means whole file
        """
        assert(isinstance(fd, io.BufferedIOBase))

        # Move the file pointer to the start of this element
        start = self.offset + bias
        fd.seek(start, io.SEEK_SET)

        obj = zlib.decompressobj()
        sz = self.size
        if step is None:
            # Read the whole file the first time
            step = sz
        total = 0
        while sz > 0:
            # get next chunk size
            chunk = min(step, sz)
            raw = fd.read(chunk)
            if len(raw) != chunk:
                raise LymeError('Too few data reading {}'.format(self))

            data = obj.decompress(raw)
            out.write(data)
            total += len(data)
            sz -= chunk
        # Small check
        if not obj.eof:
            raise LymeError('Unfinished extractor')

        if total != self.length:
            raise LymeError('Incorrect extracted size')

    def extract(self, fd, bias):
        """
        Extract from fd and write to out
        Args:
            fd: File descriptor to read
            bias: error in the file position information
        """
        assert(isinstance(fd, io.BufferedIOBase))

        # Move the file pointer to the start of this element
        start = self.offset + bias
        fd.seek(start, io.SEEK_SET)

        # Read the raw data
        raw = fd.read(self.size)
        data = zlib.decompress(raw)

        if len(data) != self.length:
            raise LymeError('Incorrect extracted size')
        return data


class LymeFile:
    """
    Open a Lyme Sfx file

    This code is based in the information from
    http://unlyme.florz.de/   (Old format, no directory flag)
    https://exelab.ru/f/index.php?action=vthread&forum=5&topic=16403

    All the paths need to be relative.
    If the file contains an absolute path the name will be transformed
    to a file name and stored in the extraction directory

    If two files have the same name, the last one in the TOC is preserved.
    """
    _Signature = b'!LYME_SFX!'
    _Version = b'1.10'
    _Chunk = 8096

    @classmethod
    def _find_signature(cls, fd):
        """
        Search for the signature in the file

        Args:
            fd: A File object
        Returns:
            suffix start position
            fd pointer at TOC start
        """
        assert(isinstance(fd, io.BufferedIOBase))

        sz = len(cls._Version) + len(cls._Signature)
        # Start searching from the end of file for the footer
        # Go to the end of the file and read the header
        try:
            fd.seek(-sz, io.SEEK_END)
        except OSError:
            raise LymeError('File too short to be a lyme')

        # before the signature the Lyme file shall have the TOC
        # The smaller Lyme file will have an empty TOC of just 0x00000000
        while fd.tell() >= 4:
            raw = fd.read(sz)

            if raw.endswith(cls._Signature):
                break

            # Ok, try one byte before
            fd.seek(-(sz + 1), io.SEEK_CUR)
        else:
            raise LymeError('Not a Lyme file [signature not found]')

        # Suffix start where the signature ends
        suffix = fd.tell()

        # Check the version
        version = raw[:len(cls._Version)]
        if version != cls._Version:
            warnings.warn(
                'Version mismatch {} != {}'.format(version, cls._Version)
            )
        # Go to start of TOC
        fd.seek(-sz, os.SEEK_CUR)
        return suffix

    @staticmethod
    def _read_toc(fd, old=False, endian=None):
        """
        Read the complete TOC

        Args:
            fd: A file object
            old: Use old TOC format
            endian: Endianness used to code the dword fields
                    Use None try to autodetect the right endian
        Returns:
            The TOC as a list of LymeInfo
            bias of the last record
        """
        assert(isinstance(fd, io.BufferedIOBase))

        # Fist 4 bytes are the number of elements
        fd.seek(-4, io.SEEK_CUR)
        raw = fd.read(4)

        if endian is None or endian == 'auto':
            # Ok, try to determine it, assume that the number of
            # files cannot be huge, so choose the one that produces
            # the smaller number of entries
            big, = struct.unpack('>I', raw)
            little, = struct.unpack('<I', raw)
            if big <= little:
                endian = '>'
                n = big
            else:
                endian = '<'
                n = little
        else:
            n, = struct.unpack(endian + 'I', raw)

        # Go back to the start of the first TOC element
        fd.seek(-4, io.SEEK_CUR)
        last = 0
        toc = []
        while len(toc) < n:
            info = LymeInfo.from_fd(fd, old, endian)
            toc.append(info)
            if info.is_dir:
                continue
            # Calculate the last position of this record to obtain bias
            last = max(last, info.offset + info.size)

        # Current position is the end of the last file stored in the
        # Lymefile, but that might not be equal to the offset value
        bias = fd.tell() - last
        return toc, bias

    def __init__(self, fd, old=False, endian=None):
        """
        Read from an existing file

        Args:
            fd: File opened in binary mode or file path
            old: Use the old format with no directory flag
            endian=One of '>' or '<'. None for autodetect
        """

        if isinstance(fd, io.BufferedIOBase):
            self._fd = fd
        else:
            self._fd = open(fd, 'rb')

        self._suffix = self._find_signature(self._fd)

        # Now read the TOC
        self._toc, self._bias = self._read_toc(self._fd, old, endian)

        # And get the length of the SFX block
        sfx = min(entry.offset for entry in self._toc if not entry.is_dir)

        # Take into account the bias for the end of the SFX block
        self._sfx = sfx + self._bias

    def extract(self, member):
        """
        Extract just one member and return it as bytes
        Args:
            member: Name of the element or LymeInfo

        Returns:
            The bytes of the data or None for directories
        """
        if isinstance(member, LymeInfo):
            if member not in self._toc:
                raise LymeError('The LymeInfo is not part of the LymeFile')

        else:
            path = pathlib.PureWindowsPath(member)
            for entry in self._toc:
                if entry.path == path:
                    member = entry
                    break
            else:
                raise LymeError('{} not found'.format(member))

        # Ok, now member is an entry of the current LymeFile
        if member.is_dir:
            return None
        return member.extract(self._fd, self._bias)

    def extractall(self, path='.', step=None):
        """
        Try to extract all the elements of the lime object
        Args:
            path: Directory to extract to
            step: Buffer size to read the files
        """
        os.makedirs(path, exist_ok=True)
        for entry in self._toc:
            assert(isinstance(entry, LymeInfo))

            if entry.path.anchor != '':
                # This is an absolute path, rename it
                absolute = entry.path.as_posix()
                # Replace the / by _
                target = absolute.replace('/', '_')
                warnings.warn('Rename {} to {}'.format(absolute, target))
            else:
                target = entry.path.as_posix()
            target = os.path.join(path, target)

            if entry.is_dir:
                os.makedirs(target, exist_ok=True)
                continue
            else:
                # Try to create any intermediate folder
                os.makedirs(os.path.dirname(target), exist_ok=True)

            with open(target, 'wb') as out:
                entry.write(self._fd, self._bias, out, step)

    def sfx(self):
        """
        Get the self extract block
        Returns:
            The bytes of the self extractor
        """
        self._fd.seek(0, io.SEEK_SET)
        return self._fd.read(self._sfx)

    def suffix(self):
        """
        Get the last extra bytes
        Returns:
            The bytes written after the footer
        """
        self._fd.seek(self._suffix)
        return self._fd.read()

    def list(self, posix=True):
        """
        list all the members
        Args:
            posix: Use posix paths
        """
        out = []
        sp = 0
        for entry in self._toc:
            if posix:
                path = entry.path.as_posix()
            else:
                path = str(entry.path)
            sp = max(sp, len(path))
            if entry.is_dir:
                out.append((path, ''))
            else:
                out.append((path, entry.length))

        for path, length in out:
            print('{} {}'.format(path.ljust(sp), length))
