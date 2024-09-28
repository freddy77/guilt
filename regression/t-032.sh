#!/usr/bin/env bash
#
# Test the import code
#

source "$REG_DIR/scaffold"

cmd setup_repo

# add a comment and start spaces to last patch in the series
# to detects a bug inserting patches in the series
sed 's,^mode,  mode # comment,' < .git/patches/master/series > .git/patches/master/series.tmp
mv .git/patches/master/series.tmp .git/patches/master/series
cmd grep ' mode ' .git/patches/master/series

cmd guilt push --all

cmd touch foo foo:baz

# invalid character
shouldfail guilt import -P foo:bar foo

# non-existant file & invalid character
shouldfail guilt import -P foo:bar foo2

# non-existant file
shouldfail guilt import -P foo foo2

# ok
cmd guilt import -P foo3 foo

# this should contain foo3
cmd guilt series

# duplicate patch name
shouldfail guilt import -P foo3 foo

# ok
cmd guilt import -P foo2 foo

# this should contain foo2
cmd guilt series

# pop all patches to check importing with an empty queue
cmd guilt pop -a

# ok
cmd guilt import foo

# this should contain foo
cmd guilt series

# duplicate patch name (implicit)
shouldfail guilt import foo

# check that bug 47 doesn't come back
cmd guilt import -P foo,bar foo

# implicitly bad patch name - invalid char
shouldfail guilt import foo:baz
