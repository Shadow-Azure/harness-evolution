#!/bin/sh
# GIT_ASKPASS helper for the harness API user (no home directory).
# Git calls this with a prompt argument; credentials come from the environment:
#   HE_GIT_PUSH_USERNAME  git username (default x-access-token)
#   HE_GIT_PUSH_TOKEN     personal access token
# Only the selected value is written to stdout; nothing is logged or stored.
set -u

case "${1:-}" in
  Username*|username*)
    printf '%s\n' "${HE_GIT_PUSH_USERNAME:-x-access-token}"
    ;;
  Password*|password*)
    printf '%s\n' "${HE_GIT_PUSH_TOKEN:-}"
    ;;
  *)
    echo "git-askpass: unsupported prompt" >&2
    exit 1
    ;;
esac
