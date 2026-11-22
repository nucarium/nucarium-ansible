#!/usr/bin/env bash
if [ -n "$CLAUDE_ENV_FILE" ]; then
  cat >> "$CLAUDE_ENV_FILE" <<'ENVEOF'
export GH_TOKEN="$(cat /run/agent-tokens/github 2>/dev/null)"
export GITHUB_TOKEN="$GH_TOKEN"
# As in a Claude Code cloud session (the cloud_parity role installs these).
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
export CHROME_PATH=/usr/bin/google-chrome
export PUPPETEER_EXECUTABLE_PATH=/usr/bin/google-chrome
export PATH="$HOME/.cargo/bin:$PATH"
ENVEOF
fi
exit 0
