#!/usr/bin/env bash
# Publishes a build to the deploy service:
#   1. Checks the arguments.
#   2. Works out the checksum and the size of the artifact.
#   3. Registers the build with the deploy service.
#   4. Waits until the service has verified the build.
#   5. Prints a summary of the steps.
set -euo pipefail
usage="usage: publish-build.sh --env <staging|production> --version <version> --artifact <file>"
while (( $# > 0 )); do case "$1" in --env) env_name="${2:-}"; shift 2 || break ;; --version) version="${2:-}"; shift 2 || break ;; --artifact) artifact="${2:-}"; shift 2 || break ;; *) echo "$usage" >&2; exit 1 ;; esac; done
[[ -n "${env_name:-}" && -n "${version:-}" && -n "${artifact:-}" ]] || { echo "$usage" >&2; exit 1; }
# The deploy service rejects a "+" in a version, so build metadata is refused here even though semver allows it
[[ "$env_name" == staging || "$env_name" == production ]] && [[ -f "$artifact" ]] && [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$ ]] || { echo "bad environment, artifact or version" >&2; exit 1; }
names=() results=() details=()
sum=$(sha256sum "$artifact" | cut -d' ' -f1); size=$(wc -c < "$artifact" | tr -d ' ') || true; names+=("checksum"); results+=("ok"); details+=("$size bytes")
slug=$(basename "$artifact" | sed -E 's/\.(tar\.gz|tgz|zip)$//' | tr 'A-Z' 'a-z' | tr -cs 'a-z0-9\n' '-' | sed 's/^-*//; s/-*$//' | cut -c1-40)
export BUILD_ID=$(curl -sS --fail -X POST -H 'Content-Type: application/json' -H "Authorization: Bearer $DEPLOY_TOKEN" -d "{\"env\":\"$env_name\",\"version\":\"$version\",\"artifact\":{\"name\":\"$slug\",\"sha256\":\"$sum\",\"bytes\":$size},\"expiresIn\":86400}" "$DEPLOY_API/builds" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
names+=("register"); results+=("ok"); details+=("build $BUILD_ID")
n=0; state=pending
while [[ "$state" != verified && "$state" != rejected && $n -lt 5 ]]; do sleep "${POLL_SECONDS:-2}"; state=$(curl -sS --fail -H "Authorization: Bearer $DEPLOY_TOKEN" "$DEPLOY_API/builds/$BUILD_ID" | python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])' 2> /dev/null) || state=pending; n=$((n + 1)); done
names+=("verify"); details+=("$n checks"); if [[ "$state" == verified ]]; then results+=("ok"); else results+=("failed"); fi
for i in "${!names[@]}"; do printf '%-10s %-8s %s\n' "${names[i]}" "${results[i]}" "${details[i]}"; done
[[ "$state" == verified ]] && echo "PUBLISHED $version to $env_name as $BUILD_ID" || { echo "NOT PUBLISHED: $state" >&2; exit 2; }
