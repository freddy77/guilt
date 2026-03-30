#!/bin/bash

set -e

if [ $# -ne 1 ]; then
	echo "Usage: $0 <tagname>"
	exit 1
fi

if [[ "$1" =~ ^v?([0-9][.0-9]+)(-rc[1-9][0-9]*)?$ ]]; then
	ver="${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
else
	echo "Wrong version specified $1" >&2
	exit 1
fi
tag="v$ver"

echo "About start release process of '`git rev-parse HEAD`' as '$tag'..."
echo "Press enter to continue."
read n

echo "1) Patching GUILT_VERSION in 'guilt'"
read n
sed -i "s,^GUILT_VERSION=\".*\"$,GUILT_VERSION=\"$ver\"," guilt
if ! grep -x -q "GUILT_VERSION=\"$ver\"" guilt; then
	echo "Version in guilt file was not updated correctly" >&2
	exit 1
fi
git add guilt
git commit -s -m "Guilt $tag"

echo "2) Tag the commit with '$tag'"
read n
git tag -a -m "Guilt $tag" "$tag"

echo "3) Generate guilt-$ver.tar.gz"
read n
git archive --format=tar --prefix=guilt-$ver/ HEAD | gzip -9 > guilt-$ver.tar.gz

echo "4) Verify the tarball"
read n
(
	op=`pwd`
	cd /tmp
	tar xzf $op/guilt-$ver.tar.gz
	cd guilt-$ver
	make test
	make doc
)
rm -rf /tmp/guilt-$ver

echo "5) Profit"

echo "We're all done, have a nice day."
