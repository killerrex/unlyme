# Unlyme

Extract files from the strange format used by i.e. Broadcom to distribute the drivers.
The characteristic of the format is the string '!SFX_LYME!' at the end of the file

Author:
  killerrex@gmail.com

License: GPLv3

This code is based in the information from
* Old format, no directory flag, written in perl: http://unlyme.florz.de/
* Some in insights about the new format (in perfect russian): https://exelab.ru/f/index.php?action=vthread&forum=5&topic=16403
* Trial and error with some files.

This means that it is easy that it does not work with a lot of files in the wild.

## Usage
You can use the module from a python3 script, or from the command line.
* List the content of a file
```bash
python3 -m lymefile -l Lyme.ly
```
* Extract the content of a file to the current directory
```bash
python3 -m lymefile --extract Lyme.ly
```
* Extract the content of an old format file to the current directory
```bash
python3 -m lymefile --extract Lyme.ly --format=old
```
* See the help
```bash
python3 -m lymefile --help
```

## General description of the format

The format is not specified anywhere, but using the information from Florian Zumbiehl <florz@florz.de>, the forum guidelines (where they refer to the new format as 'Chinese variant') and some examples from broadcom it can be something like:

* Windows SFX Block
* Data Area:
  * File 1 zlib compressed
  * File 2 zlib compressed
  ...
  * File n zib compressed
* TOC
  * toc entry #1
  * toc entry #2
  ...
  * toc entry #m
  * toc size (m)
* Version
* Signature
* ignore the rest

The file shall be read backwards, so search first for the signature, next the toc...

The signature is the binary string: '!SFX_LYME!'
The version is almost always '1.10'
The TOC size is the number of entries, as a dword, usually codded as big endian, although in recent files it is little endian. Unlyme tries to guess the format by choosing the mode that produces a smaller TOC.

Each TOC entry consists of:
offset length size 'File Path' n flag:
* offset: dword with the initial position of the compressed data in the Lyme file
* length: dword with the size of the file once expanded
* size: dword with the byte length of the compressed data
* 'File Path': Windows path of the file or directory
* n: dword with the number of bytes used to store 'File Path'
* flag: Single byte that is 0 for files and 1 for directories.

For directories, offset, length and size are 0.
In the old format the flag does not exist, so to determine if it is a folder, both offset and size must be 0 (as the zlib compressed of an empty file uses 8 bytes)

In some files the offset value has a bias so Unlyme tries to determine it using that the last byte of the last file shall be next to the TOC.
