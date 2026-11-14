#!/usr/bin/env bash
# Decide whether a Cloudflare deploy runs, as the step output "run" (true or false).
# Usage: cloudflare-gate.sh LABEL
# LABEL starts the notice, as in "Preview skipped: fork PR.". TOKEN and ACCOUNT hold the
# CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID secrets, and FORK is "true" for a pull
# request from a fork, which gets no secrets. Either case skips the deploy rather than
# failing the job, so a repo without Cloudflare set up stays green.
set -euo pipefail

missing=""
[ -n "$TOKEN" ] || missing=CLOUDFLARE_API_TOKEN
[ -n "$ACCOUNT" ] || missing="${missing:+$missing and }CLOUDFLARE_ACCOUNT_ID"
if [ "${FORK:-}" = "true" ]; then
    echo "::notice::$1 skipped: fork PR."
    echo "run=false" >>"$GITHUB_OUTPUT"
elif [ -n "$missing" ]; then
    echo "::notice::$1 skipped: $missing not set."
    echo "run=false" >>"$GITHUB_OUTPUT"
else
    echo "run=true" >>"$GITHUB_OUTPUT"
fi
