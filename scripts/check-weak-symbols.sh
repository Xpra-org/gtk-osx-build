#!/bin/sh
#
# Guard against accidentally weakly-linked system symbols.
#
# When a configure script probes for a libSystem/framework function that the
# build SDK declares with __API_AVAILABLE() above our deployment target, clang
# happily links it *weakly*: the binary builds and runs on the build machine,
# but the symbol is NULL on an older macOS and calling it crashes.  Unless the
# caller checks for NULL first, that is a latent crash on every machine older
# than the SDK-declared availability of that symbol.
#
# We have shipped this bug at least twice (see commit a1f674c "glib2 pipe2
# crash: avoid weakly-linked symbol" and patches/glib-darwin-skip-unavailable-
# functions.patch).  This script turns that class of regression into a build
# failure: it lists every weakly-linked undefined system symbol in the install
# prefix and fails if any of them is not in scripts/weak-symbols.allow.
#
# Note that a weak reference is not automatically a bug -- it is fine when the
# caller NULL-checks it (CPython's `#pragma weak inet_aton` does exactly that).
# So the allow file is a triage list, not a list of known-good practice: each
# entry should say why that symbol is safe.
#
# Usage:
#   scripts/check-weak-symbols.sh [prefix]            # check (default ~/gtk/inst)
#   scripts/check-weak-symbols.sh [prefix] --update   # rewrite the allow file
#
set -eu

prefix=${1:-$HOME/gtk/inst}
case ${2:-} in
    --update) update=1 ;;
    "")       update=0 ;;
    *)        echo "usage: $0 [prefix] [--update]" >&2; exit 2 ;;
esac

allow=$(dirname "$0")/weak-symbols.allow

if [ ! -d "$prefix" ]; then
    echo "$0: no such prefix: $prefix" >&2
    exit 2
fi

# symbol <TAB> system library, one per line, for every weak undefined symbol
# that resolves to a system library.  Requiring "(from <lib>)" is what keeps
# C++ vague-linkage symbols (weak but not system) out of the report.
scan() {
    find "$prefix" -type f \( -name '*.dylib' -o -name '*.so' -o -path "$prefix/bin/*" \) |
    while read -r f; do
        case $(file -b "$f") in Mach-O*) ;; *) continue ;; esac
        nm -m "$f" 2>/dev/null |
            sed -n 's/.*undefined.*weak external \([^ ]*\) (from \([^)]*\)).*/\1	\2	'"$(printf '%s' "${f#"$prefix"/}" | sed 's/[&/\]/\\&/g')"'/p'
    done |
    grep -v '^__availability_version_check	' |
    sort -u
}

found=$(scan)

if [ "$update" = 1 ]; then
    {
        echo "# Weakly-linked undefined system symbols that are known to be present"
        echo "# and known to be handled.  Regenerate with:"
        echo "#"
        echo "#     scripts/check-weak-symbols.sh \"\$HOME/gtk/inst\" --update"
        echo "#"
        echo "# but do not do that to silence a new entry: work out first why the"
        echo "# symbol is weak, and whether the caller NULL-checks it.  See the"
        echo "# comment at the top of check-weak-symbols.sh."
        echo "#"
        echo "# Format: <symbol> <TAB> <system library>"
        echo
        printf '%s\n' "$found" | cut -f1,2 | sort -u
    } > "$allow"
    echo "wrote $allow"
    exit 0
fi

[ -f "$allow" ] || { echo "$0: missing $allow" >&2; exit 2; }

allowed=$(grep -v '^[[:space:]]*#' "$allow" | grep -v '^[[:space:]]*$' | sort -u)

# Report the full triple (symbol, library, binary) so a failure is easy to
# triage, but match against the allow file on (symbol, library) only: which
# binary picked the symbol up is not stable across version bumps.
new=$(printf '%s\n' "$found" | while IFS='	' read -r sym lib path; do
    [ -n "$sym" ] || continue
    printf '%s\n' "$allowed" | grep -qxF "$sym	$lib" || printf '%s\t%s\t%s\n' "$sym" "$lib" "$path"
done)

if [ -n "$new" ]; then
    cat >&2 <<EOF
Weakly-linked system symbols not in $allow:

$(printf '%s\n' "$new" | awk -F'\t' '{printf "  %-46s %-14s %s\n", $1, $2, $3}')

These are NULL at runtime on macOS older than the version that introduced
them, so calling one crashes unless the caller checks for NULL.  Either patch
the package to stop using the symbol (see patches/glib-darwin-skip-unavailable-
functions.patch), or, if the caller does guard it, add it to $allow
with a comment saying so.
EOF
    exit 1
fi

echo "no unexpected weakly-linked system symbols in $prefix"
