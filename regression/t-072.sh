#!/bin/bash
#
# Test the git submodules support
#

source $REG_DIR/scaffold

function fixup_time_info
{
	touch -a -m -t "$TOUCH_DATE" ".git/patches/master/$1"
}

function check_readme
{
	content=`cat README` || exit $?
	cmd test "`echo $content`" = "$*" || exit $?
}


# The "git submodule add" command needs an upstream for the repository
# that is going to be added as a submodule.  So in order to be able to
# test the submodule support in guilt, we need to set up a separate
# repository for the submodule.  This needs to have a fixed name so
# that the .gitmodules file always is identical.  We use paths with
# spaces to ensure we support that.
#
# Using a fixed path in /tmp is a security risk, but unfortunately
# there is no better location we can use.  Don't run the guilt
# testsuite on machines you share with users you don't trust.
UPSTREAM_SUBREPO_BASE="/tmp/guilt test"
UPSTREAM_SUBREPO="$UPSTREAM_SUBREPO_BASE/test sub.git"
mkdir -p "$UPSTREAM_SUBREPO_BASE"

# Lock the upstream submodule repo, if dotlockfile is available.
# Otherwise, just continue and hope for the best.
if type dotlockfile >/dev/null 2>&1
then
	dotlockfile -r -1 -i 2 -p "$UPSTREAM_SUBREPO_BASE.lock"
	trap "dotlockfile -u '$UPSTREAM_SUBREPO_BASE.lock'" 0
fi

# Start with a clean slate.
rm -rf "$UPSTREAM_SUBREPO_BASE"

# Populate the upstream git submodule repo.
cmd git init --bare -b trunk "$UPSTREAM_SUBREPO"
OLD=`pwd`
cd "$UPSTREAM_SUBREPO_BASE"
cmd git clone "test sub.git" copy
cd copy
echo abc > README
cmd git add README
cmd git commit -m"Initial commit of sub"
check_readme abc
echo def >> README
cmd git add README
cmd git commit -m"Extend README"
check_readme abc def
echo ghi >> README
cmd git add README
cmd git commit -m"Refine README"
cmd git push
check_readme abc def ghi
cmd git checkout -b feature HEAD^^
echo jkl >> README
cmd git add README
cmd git commit -m"Featurize README"
cmd git push origin feature
cd "$OLD"

cmd setup_git_repo

cmd guilt init
cmd list_files

# Create a patch that adds a submodule.
cmd guilt new add-submodule
cmd git -c protocol.file.allow=always submodule add "$UPSTREAM_SUBREPO" sub
(cd sub && cmd git -c advice.detachedHead=false checkout HEAD^^)
cmd guilt ref
cmd cat sub/README

# Pop the patch that adds a submodule.
cmd guilt pop
fixup_time_info add-submodule
shouldfail cat sub/README
cmd list_files
cmd git status --porcelain

# Push the patch that adds a submodule.
cmd guilt push
cmd list_files
cmd cat sub/README

#
# Ensure we can't pop a patch when the submodule is dirty.
#

# Dirty by having an untracked file.
echo dirty > sub/dirty
shouldfail guilt pop
rm sub/dirty

# Dirty by having changes to a tracked file.
echo x >> sub/README
shouldfail guilt pop
(cd sub && git restore README)

# Dirty by having a different commit checked out.
(cd sub && cmd git checkout trunk^)
shouldfail guilt pop
(cd sub && cmd git checkout trunk^^)

# Now clean again: pop should succeed
cmd guilt pop

# Add a new patch on top of the one that adds a submodule.
cmd guilt push
cmd guilt new local-changes
echo z > z
cmd git add z
cmd guilt ref
cmd guilt series
cmd guilt pop
fixup_time_info local-changes
cmd list_files

#
# Ensure we can't push a patch when the submodule is dirty.
#

# Dirty by having an untracked file.
echo dirty > sub/dirty
shouldfail guilt push
rm sub/dirty

# Dirty by having changes to a tracked file.
echo x >> sub/README
shouldfail guilt push
(cd sub && git restore README)

# Dirty by having a different commit checked out.
(cd sub && cmd git checkout trunk^)
shouldfail guilt push
(cd sub && cmd git checkout trunk^^)

# Now clean again: push should succeed
cmd guilt push
cmd guilt series

#
# Add a patch that changes the commit in the submodule.
#

(cd sub && check_readme abc)
cmd guilt new update-sub
(cd sub && cmd git checkout trunk^)
(cd sub && check_readme abc def)
cmd guilt ref
cmd guilt pop
fixup_time_info update-sub
cmd list_files
# Since we popped the patch, the README should have reverted.
(cd sub && check_readme abc)

# Push a patch that changes the commit in the submodule
cmd guilt series
cmd guilt applied
cmd guilt push
cmd guilt applied
(cd sub && check_readme abc def)
cmd list_files
cmd git status --porcelain

# Pop a patch that changes the commit in the submodule
cmd guilt pop
(cd sub && check_readme abc)
cmd list_files
cmd git status --porcelain

# Push it back.  Then, change the submodule to a taskbranch.
cmd guilt push
(cd sub && cmd git checkout feature)
(cd sub && check_readme abc jkl)
shouldfail guilt new use-feature
cmd guilt new -f use-feature
cmd guilt pop
fixup_time_info use-feature
cmd guilt push
cmd list_files

# Pop many patches, including the one that creates the submodule
cmd q pop -a
shouldfail test -d sub
# Push all patches back.
cmd q push -a
cmd test -d sub
(cd sub && check_readme abc jkl)
