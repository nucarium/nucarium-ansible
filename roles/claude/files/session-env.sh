#!/usr/bin/env bash
# SessionStart hook. Adds to every new session of environment $1 the
# variables a session on this box needs, then the environment's own
# (variables in environments, group_vars/all.yml), which the env_setup role
# writes, shell-quoted and root-owned, to
# /etc/nucarium/environments/<name>/variables.sh. The same on the host and in
# a container environment, which has both folders mounted at their own paths
# and HOME=/root.
if [ -n "$CLAUDE_ENV_FILE" ]; then
  cat >> "$CLAUDE_ENV_FILE" <<'ENVEOF'
export GH_TOKEN="$(cat /run/agent-tokens/github 2>/dev/null)"
export GITHUB_TOKEN="$GH_TOKEN"
# As in a Claude Code cloud session (the cloud_parity role installs these).
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
export CHROME_PATH=/usr/bin/google-chrome
export PUPPETEER_EXECUTABLE_PATH=/usr/bin/google-chrome
# Appended, and read-only to sandboxed commands (vars/sandbox.yml).
export PATH="$PATH:$HOME/go/bin:$HOME/.cargo/bin"
ENVEOF
  # An environment's name is lower-case letters, digits and hyphens.
  case "${1:-}" in
    '' | *[!a-z0-9-]*) ;;
    *)
      variables="/etc/nucarium/environments/$1/variables.sh"
      if [ -r "$variables" ]; then
        cat "$variables" >> "$CLAUDE_ENV_FILE"
      fi
      ;;
  esac
fi
exit 0
