#!/bin/bash
set -euo pipefail

input=$(cat)
prompt=$(echo "$input" | jq -r '.user_prompt // ""')

# Extract URLs from the prompt
urls=$(echo "$prompt" | grep -oE 'https?://[^ ]+' || true)

if [ -z "$urls" ]; then
  echo '{}'
  exit 0
fi

# Calculate what fraction of the message is URLs
total_chars=$(echo "$prompt" | tr -d '[:space:]' | wc -c | tr -d ' ')
url_chars=$(echo "$urls" | tr -d '[:space:]' | wc -c | tr -d ' ')

if [ "$total_chars" -eq 0 ]; then
  echo '{}'
  exit 0
fi

ratio=$((url_chars * 100 / total_chars))

if [ "$ratio" -gt 50 ]; then
  cat <<'EOF'
{"systemMessage": "The user sent URL(s) to process. You MUST delegate to the x-reader-pipeline agent to handle the full fetch->store->archive pipeline. Do NOT process the URLs inline."}
EOF
else
  echo '{}'
fi
