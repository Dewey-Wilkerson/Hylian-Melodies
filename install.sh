#!/bin/sh
# Hylian Melodies bootstrap: fetches one pinned, checked release of the installer's source and starts the installer.
#
#   curl -fsSL <url>/install.sh | sh
#   curl -fsSL <url>/install.sh | sh -s -- --help
#
# It writes only under ${XDG_CACHE_HOME:-~/.cache}/hylian-melodies/src/ and installs nothing: no root, no packages,
# no PATH or shell changes. The installer it starts asks for your own cartridge dump and keys; nothing is uploaded.
# docs/installer.md, section 1. The release values below are filled in by tools/release.py.
#
# The whole script is one function called on the last line, so a download cut short runs nothing.

main() {
    set -eu

    HM_TAG='@HM_TAG@'
    HM_SHA256='@HM_SHA256@'
    HM_REPO_URL=${HM_REPO_URL:-'@HM_REPO_URL@'}  # (the environment may point elsewhere: tests, a mirror)
    PY_MIN_MAJOR=3
    PY_MIN_MINOR=11

    source_path= source_url= ref= print_only= answers=
    while [ $# -gt 0 ]; do
        case $1 in
            -h|--help) usage; return 0 ;;
            --version) echo "Hylian Melodies bootstrap, release $(release_name)"; return 0 ;;
            --print-only) print_only=1 ;;
            --source) need_value "$@"; shift
                case $1 in
                    *://*|git@*) source_url=$1 ;;
                    *) source_path=$1 ;;
                esac ;;
            --ref) need_value "$@"; shift; ref=$1 ;;
            --tag) need_value "$@"; shift; HM_TAG=$1 ;;
            --sha256) need_value "$@"; shift; HM_SHA256=$1 ;;
            --answers) need_value "$@"; shift; answers=$1 ;;
            *) die "unknown option: $1 (see --help)" ;;
        esac
        shift
    done

    check_system

    cache=$(cache_dir)/src
    if [ -n "$source_path" ]; then
        [ -z "$ref" ] || die "--ref goes with --source URL, not with a local folder"
        [ -f "$source_path/installer/tui.py" ] || die "not a Hylian Melodies checkout: $source_path"
        src=$(cd "$source_path" && pwd)
        note="unverified source: the local folder $src"
        if [ -n "$print_only" ]; then
            say "Would run the installer from the local folder $src (not checked)."
        fi
    elif [ -n "$source_url" ]; then
        [ -n "$ref" ] || die "--source URL needs --ref BRANCH_OR_TAG"
        case $ref in *[!A-Za-z0-9._/-]*|-*|*..*) die "--ref: not a branch or tag name: $ref" ;; esac
        have git || die "git is needed for --source URL (install it with your package manager)"
        src=$cache/ref-$(printf '%s' "$ref" | tr '/' '_')
        note="unverified source: $source_url at $ref"
        if [ -n "$print_only" ]; then
            say "Would clone $source_url at $ref (with your own git credentials) into $src (not checked)."
        else
            fetch_git
        fi
    else
        check_release_values
        src=$cache/$HM_TAG
        tarball=$cache/hylian-melodies-$HM_TAG.tar.gz
        url=$HM_REPO_URL/releases/download/$HM_TAG/hylian-melodies-$HM_TAG.tar.gz
        note="release $HM_TAG, SHA-256 checked"
        if [ -n "$print_only" ]; then
            say "Would download $url"
            say "  into $tarball, check its SHA-256 is $HM_SHA256,"
            say "  and unpack it into $src."
        else
            fetch_release
        fi
    fi

    if [ -n "$answers" ]; then
        case $answers in /*) ;; *) answers=$(pwd)/$answers ;; esac
        set -- --answers "$answers"
    else
        set --
    fi
    if [ -n "$print_only" ]; then
        say "Then: cd $src && python3 -m installer.tui --root $src --source-note \"$note\" $*"
        return 0
    fi
    cd "$src"
    if [ -n "$answers" ]; then
        exec python3 -m installer.tui --root "$src" --source-note "$note" "$@"
    fi
    # stdin is this script when it came through a pipe: the questions are asked on the terminal itself
    # (in a subshell: a failed redirection on the special builtin ":" would end the whole script in POSIX mode)
    if ! ( : </dev/tty ) 2>/dev/null; then
        die "no terminal to ask the questions on. Run it from a terminal, or without questions:
  sh install.sh --answers FILE.json   (the fields are in docs/installer.md, section 2)"
    fi
    exec python3 -m installer.tui --root "$src" --source-note "$note" </dev/tty
}

usage() {
    cat <<EOF
Hylian Melodies bootstrap (release $(release_name))

Downloads the installer's source for one release, checks its SHA-256, and starts the installer, which asks for
your own cartridge dump and console keys and builds the game on this computer. This script installs nothing
itself and never needs root; at the end the installer offers to run your package manager (with sudo).

  curl -fsSL <url>/install.sh | sh -s -- [options]
  sh install.sh [options]

Options:
  --print-only            show what would be downloaded and run, then stop
  --answers FILE.json     no questions: the installer's plan from a file (docs/installer.md, section 2)
  --tag vX.Y.Z --sha256 HEX
                          another release than the one this script names
  --source PATH           a local checkout instead of a release (development; not checked)
  --source URL --ref REF  a git repository at a branch or tag, cloned with your own git credentials (not checked)
  --version, --help

Files: only ${XDG_CACHE_HOME:-~/.cache}/hylian-melodies/src/.
EOF
}

say() { printf '%s\n' "$*"; }
die() { printf 'hylian-melodies install: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
need_value() { [ $# -ge 2 ] || die "$1 needs a value"; }

release_name() {
    case $HM_TAG in @*) echo "none: an unreleased copy" ;; *) echo "$HM_TAG" ;; esac
}

cache_dir() {
    case ${HOME:-} in /*) ;; *) die "HOME is not an absolute path" ;; esac
    case ${XDG_CACHE_HOME:-} in
        /*) echo "$XDG_CACHE_HOME/hylian-melodies" ;;
        *) echo "$HOME/.cache/hylian-melodies" ;;  # (XDG: unset or relative means the default)
    esac
}

# The command that installs a package on this distribution (only printed; never run from here).
install_hint() {
    id= like=
    if [ -r /etc/os-release ]; then
        id=$(sed -n 's/^ID=//p' /etc/os-release | tr -d '"')
        like=$(sed -n 's/^ID_LIKE=//p' /etc/os-release | tr -d '"')
    fi
    case " $id $like " in
        *" arch "*) echo "sudo pacman -S --needed $1" ;;
        *" debian "*|*" ubuntu "*) echo "sudo apt install $1" ;;
        *" fedora "*|*" rhel "*) echo "sudo dnf install $1" ;;
        *" suse "*|*" opensuse "*) echo "sudo zypper install $1" ;;
        *) echo "your package manager's package for $1" ;;
    esac
}

check_system() {
    [ "$(uname -s)" = Linux ] || die "this installer is for Linux (found $(uname -s))"
    case $(uname -m) in
        x86_64|amd64) ;;
        *) die "the game is built for x86-64 computers (found $(uname -m))" ;;
    esac
    missing=
    if ! have python3; then
        missing="python3"
    elif ! python3 -c "import sys; sys.exit(sys.version_info < ($PY_MIN_MAJOR, $PY_MIN_MINOR))" 2>/dev/null; then
        die "Python $PY_MIN_MAJOR.$PY_MIN_MINOR or newer is needed; this computer has $(python3 -c 'import platform; print(platform.python_version())' 2>/dev/null || echo 'an older one')"
    fi
    if [ -z "$source_path$source_url" ]; then
        have tar || missing="$missing tar"
        have gzip || missing="$missing gzip"
        have curl || have wget || missing="$missing curl"
        have sha256sum || have shasum || missing="$missing coreutils"
    fi
    if [ -n "$missing" ]; then
        set -- $missing
        die "missing: $*. Install with:
  $(install_hint "$*")
then run this again."
    fi
}

check_release_values() {
    case $HM_TAG in
        @*) die "this copy of install.sh is not a release (tools/release.py fills it in). Use --tag vX.Y.Z --sha256 HEX, or --source PATH for a local checkout" ;;
        v[0-9]*) ;;
        *) die "--tag: not a release tag: $HM_TAG" ;;
    esac
    case $HM_TAG in *[!A-Za-z0-9._-]*) die "--tag: not a release tag: $HM_TAG" ;; esac
    case $HM_SHA256 in @*) die "--tag needs --sha256 too (the release notes give it)" ;; esac
    HM_SHA256=$(printf '%s' "$HM_SHA256" | tr 'A-F' 'a-f')
    if [ ${#HM_SHA256} -ne 64 ]; then die "--sha256: 64 hex digits expected"; fi
    case $HM_SHA256 in *[!0-9a-f]*) die "--sha256: 64 hex digits expected" ;; esac
    case $HM_REPO_URL in
        @*) die "this copy of install.sh names no download place (tools/release.py fills it in)" ;;
        https://*|file://*) ;;
        *) die "HM_REPO_URL must be an https:// address" ;;
    esac
}

sha256_of() {
    if have sha256sum; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

download() {  # download URL FILE
    if have curl; then
        curl -fL --proto '=https,file' --retry 3 --progress-bar -o "$2" "$1"
    else
        wget -q -O "$2" "$1"
    fi
}

fetch_release() {
    mkdir -p "$cache"
    if [ -f "$tarball" ] && [ "$(sha256_of "$tarball")" = "$HM_SHA256" ]; then
        say "Using the release $HM_TAG downloaded before ($tarball)."
    else
        say "Downloading Hylian Melodies $HM_TAG from $url"
        rm -f "$tarball.part"
        download "$url" "$tarball.part" || { rm -f "$tarball.part"; die "the download failed: $url"; }
        got=$(sha256_of "$tarball.part")
        if [ "$got" != "$HM_SHA256" ]; then
            rm -f "$tarball.part"
            die "the download does not match the release's checksum, so it was not used.
  expected $HM_SHA256
  got      $got"
        fi
        mv -f "$tarball.part" "$tarball"
    fi
    # unpacked fresh each time into a new folder, then put in place (a half-unpacked folder is never used)
    rm -rf "$src.new"
    mkdir -p "$src.new"
    tar -xzf "$tarball" -C "$src.new" --strip-components=1 || { rm -rf "$src.new"; die "cannot unpack $tarball"; }
    [ -f "$src.new/installer/tui.py" ] || { rm -rf "$src.new"; die "$tarball does not hold the installer"; }
    rm -rf "$src"
    mv "$src.new" "$src"
}

fetch_git() {
    mkdir -p "$cache"
    say "Cloning $source_url at $ref"
    rm -rf "$src.new"
    git clone --quiet --depth 1 --branch "$ref" -- "$source_url" "$src.new" || { rm -rf "$src.new"; die "git clone failed"; }
    [ -f "$src.new/installer/tui.py" ] || { rm -rf "$src.new"; die "$source_url at $ref does not hold the installer"; }
    rm -rf "$src"
    mv "$src.new" "$src"
}

main "$@"
