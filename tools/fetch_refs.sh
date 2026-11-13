#!/bin/sh
# Clone the reference projects into a folder outside the repository (default ~/refs, or $HM_REFS) at pinned
# commits. Read-only study material; never copied into the tree without THIRD_PARTY_NOTICES.md (CONTRIBUTING.md).
# Skips a checkout that is already at its pin, so reruns are cheap.
set -eu
refs=${HM_REFS:-$HOME/refs}
mkdir -p "$refs"

fetch() {
    name=$1 url=$2 commit=$3
    dir=$refs/$name
    if [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null || true)" = "$commit" ]; then
        echo "$name: up to date"
        return
    fi
    if [ ! -d "$dir/.git" ]; then
        git init -q "$dir"
        git -C "$dir" remote add origin "$url"
    fi
    git -C "$dir" fetch -q --depth 1 origin "$commit"
    git -C "$dir" checkout -q --detach FETCH_HEAD
    echo "$name: $commit"
}

fetch LASRecomp              https://github.com/peiikai/LASRecomp.git              579fdad6d736c8fbf1d21943593731eb926b6659
fetch totk-pc-recomp         https://github.com/valentderah/totk-pc-recomp.git     7a37fc3c346cd6f2b3c80637effb27b880ce817b
fetch SavageWindRecomp       https://github.com/Revivedx/SavageWindRecomp.git      740b18025fe11ba03c117dbb56668db304b5043e
fetch super-odyssey-pc-recomp https://github.com/Simon3Sarkis/super-odyssey-pc-recomp.git c82448c978be8b2da4ac41cafbbe425b83d8eb87
fetch SwitchRECOMP           https://github.com/SwitchRECOMP-Dev/SwitchRECOMP.git  713c8618689afb26b904673a0f2f9901eb6baf7b
