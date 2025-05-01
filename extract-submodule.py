#!/usr/bin/env python3
# -*-mode: python; coding: utf-8 -*-

# Extract submodule information from a patch.
#
# "git apply" basically ignores changes to submodules.  So after
# running "git apply", we use this script to extract submodule
# changes, and we then apply them manually.
#
# This reads the named patch file, looking for entries like this:
#
#    diff --git a/sub b/sub
#    index a7e7183..d62f973 160000
#    --- a/sub
#    +++ b/sub
#    @@ -1 +1 @@
#    -Subproject commit a7e7183eb4d21bb19f54a6a25cc590843ebf578c
#    +Subproject commit d62f97387ef4cd200a4c5490358b6913b457e603
#
# It prints one line for each submodule update it finds:
#
#    <oldhash> <newhash> <filename>
#
# For the above example, it would print "a7e7... d62f... sub" (but the
# hashes won't be truncated).

# The patch parsing code is taken from pdiffdiff.py (see
# https://git.lysator.liu.se/pdiffdiff/pdiffdiff).  It is much more
# complex than what we need here, but the code was available and
# written by me, so for now let's use it.  /ceder

import os
import re
import sys
import getopt
import subprocess

CONSIDER_UNCHANGED = False
ASSUME_BINARY_UNCHANGED = False

class LineType:
    def __init__(self, line, match):
        self.__line = line
        self.__match = match

    def line(self):
        return self.__line

    def match(self):
        return self.__match

    def __lt__(self, other):
        if not isinstance(other, LineType):
            return NotImplemented
        return self.__line < other.__line

    def __le__(self, other):
        if not isinstance(other, LineType):
            return NotImplemented
        return self.__line <= other.__line

    def __ge__(self, other):
        if not isinstance(other, LineType):
            return NotImplemented
        return self.__line >= other.__line

    def __gt__(self, other):
        if not isinstance(other, LineType):
            return NotImplemented
        return self.__line > other.__line

    def __eq__(self, other):
        if not isinstance(other, LineType):
            return NotImplemented
        return self.__line == other.__line

    def __ne__(self, other):
        if not isinstance(other, LineType):
            return NotImplemented
        return self.__line != other.__line

    def __hash__(self):
        return hash(self.__line)

class HeaderLine(LineType):
    RE = re.compile("")

class FileHeader(LineType):
    def raw_filename(self):
        return self.match().group('filename')

    def filename(self, skipnum):
        """Strip SKIPNUM slashes."""
        raw = self.raw_filename()
        if raw == '/dev/null':
            return raw
        else:
            res = raw
            while skipnum > 0:
                res = strip_one(res)
                skipnum = skipnum - 1
            return res

    def filename_score(self):
        if self.SCORE == 0:
            return 0
        if self.raw_filename() == '/dev/null':
            return 0
        else:
            return self.SCORE

class OnlyInFileLine(FileHeader):
    RE = re.compile("^Only in (?P<dir>.*): (?P<file>.*)$")
    SCORE = 5
    def raw_filename(self):
        return self.match().group('dir') + '/' + self.match().group('file')

class BinaryLine(FileHeader):
    RE = re.compile("^Binary files (?P<filename>.*) and .* differ$")
    SCORE = 5

class IndexLine(FileHeader):
    RE = re.compile("^Index: (?P<filename>.*)$")
    SCORE = 5

class EqLine(FileHeader):
    RE = re.compile("^=+$")
    SCORE = 0

class RCSFileLine(FileHeader):
    RE = re.compile("^RCS file: .*/(?P<filename>[^/]+),v$")
    SCORE = 1

class RetrievingLine(FileHeader):
    RE = re.compile("^retrieving revision ")
    SCORE = 0

class DiffCmd(FileHeader):
    RE = re.compile("^diff .* (?P<filename>[^ ]+)$")
    SCORE = 2

class GitIndex(FileHeader):
    RE = re.compile("^index [0-9a-f]+\\.\\.[0-9a-f]+( (?P<gitmode>[0-7]+))?$")
    SCORE = 0

class GitNewFile(FileHeader):
    RE = re.compile("^new file mode [0-7]+$")
    SCORE = 0

class GitDeletedFile(FileHeader):
    RE = re.compile("^deleted file mode [0-7]+$")
    SCORE = 0

class GitModeChange(FileHeader):
    RE = re.compile("^(new|old) mode [0-7]+$")
    SCORE = 0

class FromLine(FileHeader):
    RE = re.compile("^--- (?P<filename>[^\t]+)")
    SCORE = 3

class ToLine(FileHeader):
    RE = re.compile("^\\+\\+\\+ (?P<filename>[^\t]+)")
    SCORE = 4

class FileData(LineType): pass

class HunkStart(FileData):
    RE = re.compile("^@@")

class InHunk(FileData): pass

class ContextLine(InHunk):
    RE = re.compile('^ ')

class ChangedLine(InHunk): pass

class RemovedLine(ChangedLine):
    RE = re.compile('^-')

class AddedLine(ChangedLine):
    RE = re.compile('^\\+')

class NoNewLineAtEndOfFile(InHunk):
    RE = re.compile('^\\\\ No newline at end of file$')

class EOFError(Exception): pass

def strip_one(fn):
    pos = fn.find('/')
    return fn[pos+1:]

def strip_prefix(fn, prefix):
    assert fn.startswith(prefix)
    fn = fn[len(prefix):]
    if prefix[-1] != '/':
        assert fn[0] == '/'
        fn = fn[1:]
    return fn

class LineLexer:
    def __init__(self, fp):
        self.__fp = fp
        self.__line = None
        self.__in_hunk = False
        self.__line_number = 0
        self.__val = self.__next()

    def step(self):
        if self.__val is None:
            raise EOFError("EOF already seen")
        self.__val = self.__next()

    def peek(self):
        return self.__val

    def consume(self):
        rv = self.peek()
        self.step()
        return rv

    RE_TO_TYPE = [
        IndexLine,
        EqLine,
        RCSFileLine,
        RetrievingLine,
        DiffCmd,
        GitIndex,
        GitNewFile,
        GitDeletedFile,
        GitModeChange,
        FromLine,
        ToLine,
        HunkStart,
        OnlyInFileLine,
        BinaryLine,
        HeaderLine,
        ]

    RE_TO_TYPE_HUNK = [
        ContextLine,
        RemovedLine,
        AddedLine,
        NoNewLineAtEndOfFile,
        ]

    def __match_rule(self, rules):
        for klass in rules:
            m = klass.RE.match(self.__line)
            if m is not None:
                return klass(self.__line, m)
        return None

    def __compute_linetype(self):
        if self.__in_hunk:
            rv = self.__match_rule(self.RE_TO_TYPE_HUNK)
            if rv is not None:
                return rv
            self.__in_hunk = False
        rv = self.__match_rule(self.RE_TO_TYPE)
        if isinstance(rv, HunkStart):
            self.__in_hunk = True
        return rv

    def __next(self):
        self.__line = self.__fp.readline()
        self.__line_number += 1
        if self.__line == '':
            return None
        else:
            if len(self.__line) >= 2 and self.__line[-2:] == '\r\n':
                self.__line = self.__line[:-2]
            elif len(self.__line) >= 1 and self.__line[-1:] == '\n':
                self.__line = self.__line[:-1]
            elif len(self.__line) >= 1 and self.__line[-1:] == '\r':
                self.__line = self.__line[:-1]

        return self.__compute_linetype()

    def line_number(self):
        return self.__line_number


class PatchHunk:
    def __init__(self, lexer):
        self.__start = lexer.consume()
        self.__hunk = []
        self.__changes = []
        self.__lines = None
        while isinstance(lexer.peek(), InHunk):
            if isinstance(lexer.peek(), ChangedLine):
                self.__changes.append(lexer.peek())
            self.__hunk.append(lexer.consume())

    def __lt__(self, other):
        if not isinstance(other, PatchHunk):
            return NotImplemented

        if CONSIDER_UNCHANGED:
            return self.__hunk < other.__hunk
        else:
            return self.__changes < other.__changes

    def __le__(self, other):
        if not isinstance(other, PatchHunk):
            return NotImplemented

        if CONSIDER_UNCHANGED:
            return self.__hunk <= other.__hunk
        else:
            return self.__changes <= other.__changes

    def __ge__(self, other):
        if not isinstance(other, PatchHunk):
            return NotImplemented

        if CONSIDER_UNCHANGED:
            return self.__hunk >= other.__hunk
        else:
            return self.__changes >= other.__changes

    def __gt__(self, other):
        if not isinstance(other, PatchHunk):
            return NotImplemented

        if CONSIDER_UNCHANGED:
            return self.__hunk > other.__hunk
        else:
            return self.__changes > other.__changes

    def __eq__(self, other):
        if not isinstance(other, PatchHunk):
            return NotImplemented

        if CONSIDER_UNCHANGED:
            return self.__hunk == other.__hunk
        else:
            return self.__changes == other.__changes

    def __ne__(self, other):
        if not isinstance(other, PatchHunk):
            return NotImplemented

        if CONSIDER_UNCHANGED:
            return self.__hunk != other.__hunk
        else:
            return self.__changes != other.__changes

    def __hash__(self):
        h = 0
        for line in self.__hunk:
            h = h ^ hash(line)
        return h

    def format(self, header):
        return [header + x.line() for x in [self.__start] + self.__hunk]

    def lines(self):
        if self.__lines is None:
            self.__lines = [x.line() for x in self.__hunk]
        return self.__lines

    def changed_lines(self):
        return self.__changes

    def raw_lines(self):
        return self.__hunk

    def significant_lines(self):
        if CONSIDER_UNCHANGED:
            return self.raw_lines()
        else:
            return self.changed_lines()

    def header_line(self):
        return self.__start.line()

bin_id = 0

class BinaryHunk:
    def __init__(self):
        global bin_id

        self.__bin_id = bin_id
        bin_id += 1

    def __lt__(self, other):
        if not isinstance(other, BinaryHunk):
            return NotImplemented

        return self.__bin_id < other.__bin_id

    def __le__(self, other):
        if not isinstance(other, BinaryHunk):
            return NotImplemented

        return self.__bin_id <= other.__bin_id

    def __ge__(self, other):
        if not isinstance(other, BinaryHunk):
            return NotImplemented

        return self.__bin_id >= other.__bin_id

    def __gt__(self, other):
        if not isinstance(other, BinaryHunk):
            return NotImplemented

        return self.__bin_id > other.__bin_id

    def __eq__(self, other):
        if not isinstance(other, BinaryHunk):
            return NotImplemented

        return self.__bin_id == other.__bin_id

    def __ne__(self, other):
        if not isinstance(other, BinaryHunk):
            return NotImplemented

        return self.__bin_id != other.__bin_id

    def __hash__(self):
        return hash(self.__bin_id)

    def format(self, header):
        return []

    def lines(self):
        return []

    def significant_lines(self):
        return []

    def header_line(self):
        return "+- (above binary diff may or may not be the same)"

class PatchFile:
    def __init__(self, lexer, skipnum, renames):
        self.__header = []
        self.__hunks = []
        self.__fn = None
        self.__score = 0
        while isinstance(lexer.peek(), FileHeader):
            line = lexer.peek()
            lexer.step()
            self.__header.append(line)
            if line.filename_score() > self.__score:
                self.__score = line.filename_score()
                self.__fn = line.filename(skipnum)
                if renames is not None and self.__fn in renames:
                    self.__fn = renames[self.__fn]
            if isinstance(line, OnlyInFileLine):
                return
            if isinstance(line, BinaryLine):
                if not ASSUME_BINARY_UNCHANGED:
                    self.__hunks.append(BinaryHunk())
                return
        while isinstance(lexer.peek(), HunkStart):
            self.__hunks.append(PatchHunk(lexer))

    def filename(self):
        return self.__fn

    def summary(self):
        print("        Header: %d lines" % len(self.__header))
        print("        Hunks: %d" % len(self.__hunks))

    def submodule_change(self):
        if len(self.__hunks) != 1:
            return None
        is_submodule = False
        for header in self.__header:
            if isinstance(header, GitIndex):
                if header.match().group("gitmode") == "160000":
                    is_submodule = True
        if not is_submodule:
            return None
        hunk = self.__hunks[0]
        raw = hunk.raw_lines()
        if len(raw) != 2:
            return None
        if not isinstance(raw[0], RemovedLine):
            return None
        if not isinstance(raw[1], AddedLine):
            return None
        parts = raw[0].line().split()
        if len(parts) != 3 or parts[0] != "-Subproject" or parts[1] != "commit":
            return None
        from_commit = parts[2]
        parts = raw[1].line().split()
        if len(parts) != 3 or parts[0] != "+Subproject" or parts[1] != "commit":
            return None
        to_commit = parts[2]
        return (self.__fn, from_commit, to_commit)

class PatchParser:
    def __init__(self, fn, skipnum, handle_git, renames=None):

        if handle_git and fn.startswith("git:"):
            self.__filename = fn[4:]
            proc = subprocess.Popen(["git", "show", fn[4:]],
                                    text=True,
                                    stdout=subprocess.PIPE)
            fp = proc.stdout
        else:
            self.__filename = fn
            proc = None
            fp = open(fn, encoding="iso-8859-1")
        lexer = LineLexer(fp)

        self.__header = []
        while isinstance(lexer.peek(), HeaderLine):
            self.__header.append(lexer.consume())

        self.__files = {}
        while isinstance(lexer.peek(), FileHeader):
            file = PatchFile(lexer, skipnum, renames)
            self.__files.setdefault(file.filename(), []).append(file)

        self.__footer = []
        while isinstance(lexer.peek(), HeaderLine):
            self.__footer.append(lexer.consume())

        if lexer.peek() is not None:
            sys.stderr.write(
                "%s:%d: warning: malformed patch, treated as footer.\n" % (
                fn, lexer.line_number()))
            while lexer.peek() is not None:
                self.__footer.append(lexer.consume())

        fp.close()

    def filename(self):
        return self.__filename

    def summary(self):
        print("  Filename:", self.filename())
        print("    Header: %d lines" % len(self.__header))
        print("    Footer: %d lines" % len(self.__footer))
        print("    Patched files: %d" % len(self.__files))
        for fn, files in list(self.__files.items()):
            print("      %s" % fn)
            for file in files:
                file.summary()

    def submodule_changes(self):
        res = []
        for fn, files in self.__files.items():
            for file in files:
                change = file.submodule_change()
                if change is not None:
                    res.append(change)
        return res

def usage(exval):
    if exval == os.EX_OK:
        fp = sys.stdout
    else:
        fp = sys.stderr
    fp.write("Usage: %s [ opts ] patch\n" % os.path.basename(sys.argv[0]))
    fp.write("\nRecognized options:\n\n")
    fp.write(" -h --help         Show this help.\n")
    fp.write("\n")
    fp.flush()
    sys.exit(exval)

def main(argv):
    opts, args = getopt.getopt(argv[1:], 'h', ['help'])

    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage(os.EX_OK)

    if len(args) != 1:
        usage(os.EX_USAGE)

    a = PatchParser(args[0], 1, False)

    for file, old, new in a.submodule_changes():
        print(old, new, file)


if __name__ == '__main__':
    main(sys.argv)
