#!/usr/bin/env bash
#
# Test some internal functions defined in guilt script
#

source "$REG_DIR/scaffold"

cmd setup_git_repo
cmd guilt init

# build a fake "guilt-test2" to use guilt internal functions
for f in "$REG_DIR/../os."*; do
	ln -s "$f" .
done
ln -s "$REG_DIR/../guilt" mycmd
cp "$REG_DIR/guilt-test2" .

# run our test script
./mycmd test2
