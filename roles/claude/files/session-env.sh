#!/usr/bin/env bash
if [ -n "$CLAUDE_ENV_FILE" ]; then
  cat >> "$CLAUDE_ENV_FILE" <<'ENVEOF'
export GH_TOKEN="$(cat /run/agent-tokens/github 2>/dev/null)"
export GITHUB_TOKEN="$GH_TOKEN"
ENVEOF
fi
exit 0
