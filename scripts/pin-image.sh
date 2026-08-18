#!/usr/bin/env bash
#
# Pin a published menu-app image into the homelab Ansible inventory.
#
#   ./scripts/pin-image.sh 1.2.0
#   ./scripts/pin-image.sh 1.2.0 sha256:abc123...
#
# valhalla's compose file is rendered by Ansible from the homelab repo, so the
# deployable artifact is the `images.menu_app` line in that inventory -- not
# anything on the host. This script resolves the tag to an immutable digest and
# rewrites that line. Applying it is a separate, deliberate Ansible run.
#
set -euo pipefail

VERSION="${1:-}"
DIGEST="${2:-}"
IMAGE="${MENU_IMAGE:-ghcr.io/julietkiloromeo/menu-app}"
HOMELAB="${HOMELAB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../homelab" 2>/dev/null && pwd || true)}"
HOST_VARS_REL="ansible/inventory/host_vars/valhalla/main.yml"

if [[ -z "$VERSION" ]]; then
    cat >&2 <<USAGE
usage: $(basename "$0") <version> [sha256:digest]

  <version>   published image tag, e.g. 1.2.0
  [digest]    optional; resolved from the registry when omitted.
              The publish workflow prints it in its job summary.

environment overrides:
  MENU_IMAGE    image repository   (default: $IMAGE)
  HOMELAB_DIR   homelab checkout   (default: ../homelab)
USAGE
    exit 64
fi

VERSION="${VERSION#v}"

if [[ -z "$HOMELAB" || ! -f "$HOMELAB/$HOST_VARS_REL" ]]; then
    echo "ERROR: could not find $HOST_VARS_REL under '${HOMELAB:-<unset>}'." >&2
    echo "       Set HOMELAB_DIR to your homelab checkout." >&2
    exit 1
fi

HOST_VARS="$HOMELAB/$HOST_VARS_REL"

if [[ -z "$DIGEST" ]]; then
    echo "==> Resolving digest for ${IMAGE}:${VERSION}"
    if command -v skopeo >/dev/null 2>&1; then
        DIGEST="$(skopeo inspect --format '{{.Digest}}' "docker://${IMAGE}:${VERSION}")"
    elif command -v podman >/dev/null 2>&1; then
        DIGEST="$(podman manifest inspect "${IMAGE}:${VERSION}" 2>/dev/null \
            | awk -F'"' '/"digest"/ {print $4; exit}')"
    fi
fi

if [[ -z "$DIGEST" ]]; then
    cat >&2 <<'ERR'
ERROR: could not resolve the digest automatically.

The image is private, so this needs registry access. Either:
  - pass the digest explicitly (the publish workflow prints it), or
  - authenticate:  podman login ghcr.io
ERR
    exit 1
fi

if [[ "$DIGEST" != sha256:* ]]; then
    echo "ERROR: digest must start with 'sha256:' (got '$DIGEST')" >&2
    exit 1
fi

PINNED="${IMAGE}:${VERSION}@${DIGEST}"
echo "==> ${PINNED}"

NEW_IMAGE="$PINNED" python3 - "$HOST_VARS" <<'PY'
import os, re, sys

path = sys.argv[1]
new_image = os.environ["NEW_IMAGE"]
text = open(path).read()

pattern = re.compile(r'(?m)^(\s*menu_app:\s*)"[^"]*"\s*$')
match = pattern.search(text)
if not match:
    sys.exit(f"ERROR: no 'menu_app:' image entry found in {path}")

previous = re.search(r'"([^"]*)"', match.group(0)).group(1)
if previous == new_image:
    print(f"--> already pinned to this image; nothing to do")
    sys.exit(0)

open(path, "w").write(pattern.sub(lambda m: f'{m.group(1)}"{new_image}"', text, count=1))
print(f"--> was: {previous}")
print(f"--> now: {new_image}")
PY

cat <<NEXT

Updated $HOST_VARS_REL in $HOMELAB

Next:
  cd $HOMELAB/ansible
  bin/deploy valhalla --check --diff -K    # review
  bin/deploy valhalla -K                   # apply

Then commit the inventory change in the homelab repo.
NEXT
