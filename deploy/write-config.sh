#!/bin/sh
# Writes the frontend configuration from environment variables.
# Usage: write-config.sh [output path]   (default: the nginx web root inside the container)
set -eu

: "${SUPABASE_URL:?Set SUPABASE_URL to the Supabase project URL}"
: "${SUPABASE_ANON_KEY:?Set SUPABASE_ANON_KEY to the Supabase anon (public) key}"

target="${1:-/usr/share/nginx/html/js/config.js}"

cat > "$target" <<CONFIG
// Generated at deploy time by deploy/write-config.sh. Do not edit.
export const SUPABASE_URL = '${SUPABASE_URL}';
export const SUPABASE_ANON_KEY = '${SUPABASE_ANON_KEY}';
export const STORY_API_URL = '${STORY_API_URL:-}';
CONFIG

echo "write-config.sh: wrote $target"
