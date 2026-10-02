#!/usr/bin/env bash
# Build the cos-config SRPM + RPM in a clean Fedora container.
#
#   rpm/build-rpm.sh [--rel 45] [--ref HEAD]
#
# The source tarball is made with `git archive` from --ref, with the same
# layout GitHub uses for the release tarball (cos-config-<version>/). Output
# goes to out/rpm/ (git-ignored). Nothing is signed or published here.
set -euo pipefail

REL=45
REF=HEAD
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rel) REL="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    *) echo "usage: $0 [--rel N] [--ref GITREF]" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPEC="$ROOT/rpm/cos-config.spec"
VERSION="$(sed -n 's/^Version:[[:space:]]*//p' "$SPEC")"
OUT="$ROOT/out/rpm"
mkdir -p "$OUT"

git -C "$ROOT" archive --format=tar.gz --prefix="cos-config-$VERSION/" \
  -o "$OUT/cos-config-$VERSION.tar.gz" "$REF"

podman run --rm -v "$OUT:/out:Z" -v "$SPEC:/cos-config.spec:ro,Z" \
  "registry.fedoraproject.org/fedora:$REL" bash -euo pipefail -c '
    dnf -y -q install rpm-build dnf-plugins-core rpmlint >/dev/null
    dnf -y -q builddep /cos-config.spec >/dev/null
    mkdir -p ~/rpmbuild/SOURCES
    cp /out/cos-config-*.tar.gz ~/rpmbuild/SOURCES/
    rpmbuild -ba /cos-config.spec
    cp ~/rpmbuild/SRPMS/*.src.rpm ~/rpmbuild/RPMS/noarch/*.rpm /out/
    rpmlint /cos-config.spec /out/*.rpm || true
  '
ls -1 "$OUT"/*.rpm
