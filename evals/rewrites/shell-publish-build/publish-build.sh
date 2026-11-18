#!/usr/bin/env bash
# Publishes a build to the deploy service, then waits until the service has verified it.
set -euo pipefail

readonly USAGE="usage: publish-build.sh --env <staging|production> --version <version> --artifact <file>"
# The deploy service rejects a "+" in a version, so build metadata is refused here even though semver allows it
readonly VERSION_PATTERN='^[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$'
readonly MAX_STATUS_CHECKS=5
readonly BUILD_EXPIRY_SECONDS=86400

# One summary row per step, kept as parallel lists because bash has no records.
names=() results=() details=()

main() {
  parse_arguments "$@"
  if ! is_valid_request; then
    echo "bad environment, artifact or version" >&2
    exit 1
  fi
  record_artifact_details
  register_build
  wait_until_verified
  print_summary
  report_outcome
}

parse_arguments() {
  while (( $# > 0 )); do
    case "$1" in
      --env) env_name="${2:-}"; shift 2 || break ;;
      --version) version="${2:-}"; shift 2 || break ;;
      --artifact) artifact="${2:-}"; shift 2 || break ;;
      *) echo "$USAGE" >&2; exit 1 ;;
    esac
  done
  if [[ -z "${env_name:-}" || -z "${version:-}" || -z "${artifact:-}" ]]; then
    echo "$USAGE" >&2
    exit 1
  fi
}

is_valid_request() {
  [[ "$env_name" == staging || "$env_name" == production ]] \
    && [[ -f "$artifact" ]] \
    && [[ "$version" =~ $VERSION_PATTERN ]]
}

record_artifact_details() {
  artifact_sha256=$(sha256sum "$artifact" | cut -d' ' -f1)
  artifact_bytes=$(wc -c < "$artifact" | tr -d ' ')
  artifact_slug=$(slug_of "$(basename "$artifact")")
  add_summary_row "checksum" "ok" "$artifact_bytes bytes"
}

# "My Build_V2 (final).tgz" becomes "my-build-v2-final": no archive extension, lower case, dashes, 40 characters at most.
slug_of() {
  printf '%s\n' "$1" \
    | sed -E 's/\.(tar\.gz|tgz|zip)$//' \
    | tr 'A-Z' 'a-z' \
    | tr -cs 'a-z0-9\n' '-' \
    | sed 's/^-*//; s/-*$//' \
    | cut -c1-40
}

register_build() {
  local request_body
  request_body=$(printf '{"env":"%s","version":"%s","artifact":{"name":"%s","sha256":"%s","bytes":%s},"expiresIn":%s}' \
    "$env_name" "$version" "$artifact_slug" "$artifact_sha256" "$artifact_bytes" "$BUILD_EXPIRY_SECONDS")
  # Reported, kept: export hides a failed registration, so the run goes on with an empty build id.
  export BUILD_ID=$(curl -sS --fail -X POST -H 'Content-Type: application/json' -H "Authorization: Bearer $DEPLOY_TOKEN" -d "$request_body" "$DEPLOY_API/builds" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
  add_summary_row "register" "ok" "build $BUILD_ID"
}

wait_until_verified() {
  status_check_count=0
  build_state=pending
  while [[ "$build_state" != verified && "$build_state" != rejected ]] && (( status_check_count < MAX_STATUS_CHECKS )); do
    sleep "${POLL_SECONDS:-2}"
    # Reported, kept: a failed status request counts as pending.
    build_state=$(fetch_build_state) || build_state=pending
    status_check_count=$((status_check_count + 1))
  done
  if [[ "$build_state" == verified ]]; then
    add_summary_row "verify" "ok" "$status_check_count checks"
  else
    add_summary_row "verify" "failed" "$status_check_count checks"
  fi
}

fetch_build_state() {
  curl -sS --fail -H "Authorization: Bearer $DEPLOY_TOKEN" "$DEPLOY_API/builds/$BUILD_ID" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])' 2> /dev/null
}

add_summary_row() {
  names+=("$1")
  results+=("$2")
  details+=("$3")
}

print_summary() {
  for row_index in "${!names[@]}"; do
    printf '%-10s %-8s %s\n' "${names[row_index]}" "${results[row_index]}" "${details[row_index]}"
  done
}

report_outcome() {
  if [[ "$build_state" != verified ]]; then
    echo "NOT PUBLISHED: $build_state" >&2
    exit 2
  fi
  echo "PUBLISHED $version to $env_name as $BUILD_ID"
}

main "$@"
