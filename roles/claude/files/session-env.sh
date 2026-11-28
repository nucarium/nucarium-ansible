#!/usr/bin/env bash
# SessionStart hook. Adds to every new session of environment $1 the
# variables a session on this box needs, then the environment's own
# (variables in environments, group_vars/all.yml), which the env_setup role
# writes, shell-quoted and root-owned, to
# /etc/nucarium/environments/<name>/variables.sh. The same on the host and in
# a container environment, which has both folders mounted at their own paths
# and HOME=/root.
#
# Last, on the host, the environment's secret variables (secret_variables),
# from secret-variables.sh beside it, which only root and the agent user
# read. Claude Code runs what is in CLAUDE_ENV_FILE ahead of each command,
# having read it itself, so the values are copied into it, and the file is
# then the agent user's alone. Sandboxed commands may read neither file (the
# claude role's denyRead); each has the variables themselves. A container
# environment has no such file: its secret variables are its container's,
# from Podman secrets.
if [ -n "$CLAUDE_ENV_FILE" ]; then
  cat >> "$CLAUDE_ENV_FILE" <<'ENVEOF'
# The GitHub App's token when it can be read; else, in a container
# environment, its own GITHUB_TOKEN, a secret variable, as GH_TOKEN too.
if [ -r /run/agent-tokens/github ] || [ -z "${GITHUB_TOKEN:-}" ]; then
  export GH_TOKEN="$(cat /run/agent-tokens/github 2>/dev/null)"
  export GITHUB_TOKEN="$GH_TOKEN"
else
  export GH_TOKEN="$GITHUB_TOKEN"
fi
# As in a Claude Code cloud session (the cloud_parity role installs these).
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
export CHROME_PATH=/usr/bin/google-chrome
export PUPPETEER_EXECUTABLE_PATH=/usr/bin/google-chrome
# GitHub Packages' token as NODE_AUTH_TOKEN, the name repositories' READMEs
# give it in their ~/.npmrc line, so that such a line works here too. A
# container environment has it already (a Podman secret); on the host it is
# the token in the agent user's ~/.npmrc.
if [ -z "${NODE_AUTH_TOKEN:-}" ]; then
  NODE_AUTH_TOKEN="$(sed -n 's#^//npm\.pkg\.github\.com/:_authToken=\([^$].*\)#\1#p' "$HOME/.npmrc" 2>/dev/null | head -n 1)"
  if [ -n "$NODE_AUTH_TOKEN" ]; then export NODE_AUTH_TOKEN; else unset NODE_AUTH_TOKEN; fi
fi
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
      secrets="/etc/nucarium/environments/$1/secret-variables.sh"
      if [ -r "$secrets" ]; then
        chmod 600 "$CLAUDE_ENV_FILE" && cat "$secrets" >> "$CLAUDE_ENV_FILE"
      fi
      ;;
  esac
fi
exit 0
