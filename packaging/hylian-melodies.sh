#!/bin/sh
# /usr/bin/hylian-melodies: start Hylian Melodies from the player's own writable folder.
# The game is installed read-only in /opt/hylian-melodies and finds its data next to its own executable
# (/proc/self/exe), where it also writes settings, saves, logs and caches. So each player gets
# $XDG_DATA_HOME/hylian-melodies (~/.local/share/hylian-melodies) with a copy of the executable (a symlink would
# resolve back to /opt) and symlinks to everything else. HM_GAME_DIR / HM_SUPPORT_DIR override the system folders
# (the AppImage's AppRun points them into the mounted image; tests). Arguments go to the game (--fullscreen, --windowed). Settings, including the ones the installer
# asks about, are the game's own hylian-melodies.ini in that folder (installer/options.py).
set -eu

game=${HM_GAME_DIR:-/opt/hylian-melodies}
support=${HM_SUPPORT_DIR:-/usr/share/hylian-melodies-recomp}
exe=hylian-melodies
settings=hylian-melodies.ini
caches="cache logs"  # (the folders the game writes into)

case ${HOME:-} in
    /*) ;;
    *) echo "hylian-melodies: HOME is not an absolute path" >&2; exit 1 ;;
esac
if [ ! -x "$game/$exe" ]; then
    echo "hylian-melodies: $game/$exe not found (is hylian-melodies-recomp installed?)" >&2
    exit 1
fi
case ${XDG_DATA_HOME:-} in
    /*) data=$XDG_DATA_HOME ;;
    *) data=$HOME/.local/share ;;  # (XDG: unset or relative means the default)
esac
dir=$data/hylian-melodies

# 1. the folder, saves, the cache folders the game writes into, the marker the package's hooks look for
mkdir -p "$dir/profile"
for c in $caches; do mkdir -p "$dir/$c"; done
[ -e "$dir/.hylian-melodies" ] || printf '%s\n' "Set up by /usr/bin/hylian-melodies; removing the package deletes the executable copy and the symlinks here; your saves, settings, mods and caches stay" > "$dir/.hylian-melodies"

# 2. the executable copy, renewed when the installed one changes (size and mtime)
stamp=$(stat -c '%s %Y' "$game/$exe")
if [ ! -f "$dir/$exe" ] || [ -L "$dir/$exe" ] || [ "$(cat "$dir/.stamp" 2>/dev/null || true)" != "$stamp" ]; then
    cp -f "$game/$exe" "$dir/$exe.new"
    chmod 755 "$dir/$exe.new"
    mv -f "$dir/$exe.new" "$dir/$exe"
    printf '%s\n' "$stamp" > "$dir/.stamp"
fi

# 3. prune links into the install whose target is gone (a file a new release dropped)
prune() {
    for l in "$1"/* "$1"/.[!.]*; do
        [ -L "$l" ] || continue
        t=$(readlink "$l")
        # (an AppImage is mounted at a new /tmp/.mount_* folder each start: links into an earlier one go too)
        case $t in "$game"/*|*/.mount_*/opt/hylian-melodies/*) [ -e "$t" ] || rm -f "$l" ;; esac
    done
}
prune "$dir"
for c in $caches; do prune "$dir/$c"; done

# 4. link everything else; a real file or folder of the player's own always wins
link() {  # link <target> <destination>
    if [ -e "$2" ] && [ ! -L "$2" ]; then return 0; fi
    ln -sfn "$1" "$2"
}
for e in "$game"/* "$game"/.[!.]*; do
    [ -e "$e" ] || continue
    n=${e##*/}
    case " $exe profile $caches " in *" $n "*) continue ;; esac
    link "$e" "$dir/$n"
done
for c in $caches; do
    [ -d "$game/$c" ] || continue
    for e in "$game/$c"/* "$game/$c"/.[!.]*; do
        [ -e "$e" ] || continue
        link "$e" "$dir/$c/${e##*/}"
    done
done

# 5. settings: seeded once (an upgrade's kept copy first, else the package default), never touched again
if [ ! -e "$dir/$settings" ]; then
    if [ -f "$dir/$settings.upgrade-keep" ]; then
        mv -f "$dir/$settings.upgrade-keep" "$dir/$settings"
    elif [ -f "$support/$settings" ]; then
        cp "$support/$settings" "$dir/$settings"
    fi
fi

cd "$dir"
# (the game reads HM_GAME_DIR as its data folder: it must use this player's folder, not the read-only install)
unset HM_GAME_DIR HM_SUPPORT_DIR
exec "$dir/$exe" "$@"
