# Changelog

Every change to the settings in `group_vars/all.yml` and `inventory.ini` is
listed here, because the installer at `nucarium.sh` and your own copy of those
two files both depend on their names.

## The base image of container environments

This entry has no version number of its own: the release that carries it is
numbered when it is published.

The first step towards running each environment in its own container. An
environment can now say `runtime: container`, and the playbook then builds
the image such environments start from: Ubuntu 24.04 with what a Claude Code
cloud session has, for root. The environment itself still runs on the host
until a later release.

### Settings added

One optional key in each entry of `environments`:

| Setting | Default | What it is |
|---|---|---|
| `runtime` | `host` | Where the environment runs: `host` (on the box as the agent user, as before) or `container`, which is being built and for now only builds the base image. |

No setting is renamed or removed, and a settings file without `runtime`
works as it is. A value other than `host` or `container` stops the
playbook. The image is built from the existing pins: `go_version`,
`node_version`, `playwright_version`, `chrome_for_testing_version` and
`gradle_version`.

### Roles and tags

| Role | What changed |
|---|---|
| `env_runtime` | New, tag `env_runtime`. With at least one environment set to `runtime: container`, builds `localhost/nucarium-base:<hash>` in the agent user's Podman from `roles/env_runtime/files/base/Containerfile` and tags it `:current`; the hash is of the Containerfile, what it copies and the pins, so it is built again only when one of them changes. With none, it does nothing. |
| `cloud_parity` | `pw-install` can run Playwright with another Node's `npx` (`PW_INSTALL_NPX`); on the box it still uses `/opt/node24`. |

### A box built with an earlier copy of the recipe

Nothing to do: with no environment set to `runtime: container`, nothing
changes. To build the base image, set it on an environment and run
`ansible-playbook site.yml --tags env_runtime`. The first build downloads
and installs several gigabytes and takes a while; it touches no agent server
or session.

## Environments set up like a cloud environment

This entry has no version number of its own: the release that carries it is
numbered when it is published.

Each environment can now have what a Claude Code cloud environment has: its
own network access, more hosts, environment variables and a setup script.
They are set on the box, and `nucleated` reports a summary to Nucarium Watch,
which shows it and says when a setup script fails.

### Settings added

Four optional keys in each entry of `environments`:

| Setting | Default | What it is |
|---|---|---|
| `network` | `limited` | What commands in the environment's sessions may reach: `none`, `limited` (the hosts a cloud session reaches by default, plus `sandbox_extra_allowed_domains`) or `full` (any host). |
| `allowed_hosts` | `[]` | More hosts for `limited`, on top of that list. |
| `variables` | `{}` | `NAME: value` lines set in every new session of the environment. Not secret. |
| `setup_script` | none | A bash script run as root in `/root` (the nucleus's path is in `NUCLEUS_ROOT`) before the agent server starts: at every boot, and again whenever it changes. |

No setting is renamed or removed. A settings file from before these existed
works as it is, and each environment keeps the network it had. A key the
recipe does not know in an entry of `environments` now stops the playbook,
where before it was ignored.

Every value in `variables` must be quoted text, and the playbook refuses one
that is not: unquoted, YAML turns `3.10` into `3.1` and `0755` into `493`. A
script or a value with `{{`, `{%` or `{#` in it, such as `${#list[@]}` or
`docker ps --format '{{.Names}}'`, needs `!unsafe` after its key
(`setup_script: !unsafe |`), or Ansible reads it as a template; the playbook
then stops and names the environment and the key.

`network` governs the commands agents run in the sandbox. Claude Code's own
WebFetch tool is not one of them: even with `none`, it can fetch a page once
a permission prompt is approved.

### Roles and tags

| Role | What changed |
|---|---|
| `claude` | Each login's sandbox network follows its environment's `network` and `allowed_hosts`. The session hook also adds the environment's variables. |
| `env_setup` | New, tag `env_setup`. Writes each environment's variables and setup script under `/etc/nucarium/environments/<name>/`, installs `nucarium-env-setup@.service`, which runs the script at boot and when it changes, and writes `/var/lib/nucarium/environments/<name>.json`, the summary `nucleated` reports. |
| `agent_servers` | An agent server waits while its environment's setup script runs, and starts whether it succeeded or not. |

### A box built with an earlier copy of the recipe

Run `ansible-playbook site.yml --tags claude,env_setup,agent_servers`.
Nothing is restarted. New sessions get the new settings, and each agent
server waits for its setup script from its next restart on. Watch shows the
summary once `nucleated` is a release that reports it.

## The UPS state and the box's own notifier

This entry has no version number of its own: the release that carries it is
numbered when it is published.

`nucleated` now reports when the box is running on battery, and can tell you
itself when it cannot reach Nucarium Watch.

### Settings added

| Setting | Default | What it is |
|---|---|---|
| `box_notify_url` | `""` | An address of your own that the box posts to when it cannot reach Watch: once after ten minutes, once for each session that starts waiting for you while that lasts, and once when Watch answers again. `https://`, or `http://` for a service on the box itself, with no username or password. Empty means the box posts nowhere. |
| `secret_refs.box_notify_token` | `""` | A 1Password reference to the token for that address, sent as a bearer token. Empty means none is sent. |

No setting is renamed or removed. A settings file from before these two
existed works as it is: both read as empty.

### Roles and tags

| Role | What changed |
|---|---|
| `day2` | `nucleated`'s configuration gains `[ups]`, with the UPS's name, when `nut_enabled` is true, and `[notify]` when `box_notify_url` is set. The notifier's token is stored in `~agent/.config/nucleated/notify-token`, readable only by the agent user, left out of the nightly backup, and removed when the address or its reference is emptied. |

### A box built with an earlier copy of the recipe

Run `ansible-playbook site.yml --tags day2`. Nothing is restarted:
`nucleated` reads its changed configuration by itself. Both sections need a
release of `nucleated` that knows them; an earlier one ignores them, so
upgrade it first (`--tags workspace`).

## 0.1.0

The recipe is rebuilt around the two binaries that now do the work on the box:
`nucleate`, the workspace CLI, and `nucleated`, the box daemon. Reporting goes
to Nucarium Watch or nowhere.

### Settings added

| Setting | Default | What it is |
|---|---|---|
| `environments` | one entry, `name: main`, `capacity: 12` | A list with one entry per Claude login. Each entry has a `name`, an optional `config_dir` (a full path; left out, it is `~/.claude` in the agent user's home) and an optional `capacity` (left out, 12). |
| `watch_target` | `hosted` | Where the box reports: `hosted` is Nucarium Watch, `none` is nowhere. There is no address setting, because Watch is hosted only. |
| `nucleate_version` | `"0.1.0"` | The release of `nucleate` and `nucleated` to install. |
| `nucleate_sha256` | the published checksum of 0.1.0 | The SHA-256 of that release's x86_64 Linux archive. The download is refused unless it matches. A value of all zeros stops the playbook, unless `nucleate_local_archive` is set. |
| `nucleate_local_archive` | `""` | A `.tar.gz` on your workstation to install instead of the release, for testing. |
| `secret_refs.watch_machine_token` | `""` | A 1Password reference to a Nucarium Watch machine token. Empty means you run `nucleate login` on the box. |

### Settings renamed or moved

| Before | Now | Note |
|---|---|---|
| `agents_capacity` | `environments[].capacity` | Capacity is set per environment. |
| inventory group `[nucs]` | `[boxes]` | In `inventory.ini`. Both playbooks use `hosts: boxes`. |
| `secret_refs.github_app_pem: op://Infra/nuc-agent-app/private-key.pem` | `op://Infra/agentbox/github-app-private-key.pem` | Only the example value changed, so that every example reference sits under the box's own item. |

A value in `repos` may now be written `owner/name` for a repository outside
`github_org`. A bare name still means a repository in `github_org`.

### Settings removed

| Setting | Why |
|---|---|
| `company` | It only titled the push notifications, which are gone. Watch groups boxes by account. |
| `push_url`, `secret_refs.push_token` | The notify hook is replaced by `nucleated hook`, and alerts come from Watch. |
| `heartbeat_url`, `secret_refs.heartbeat_token` | The heartbeat script and timer are replaced by `nucleated`, which reports to Watch. |

### Settings unchanged

`operator_user`, `agent_user`, `timezone`, `lan_ssh_cidr`, `tailscale_tag`,
`git_user_name`, `git_user_email`, `github_org`, `repos`,
`github_app_client_id`, `github_app_installation_id`, `agents_memory_high`,
`agents_memory_max`, `nut_enabled`, `ups_name`, `ups_description`,
`ups_charge_low`, `ups_runtime_low`, `ups_offdelay`, `ups_ondelay`,
`go_version`, `node_version`, `hcp_mode`, and in `secret_refs`:
`become_password`, `luks_passphrase`, `grub_password`, `tailscale_auth_key`,
`ubuntu_pro_token`, `npm_token`, `hcp_token`, `vault_read_token`,
`restic_repository`, `restic_password`, `restic_access_key_id`,
`restic_secret_access_key`.

### Roles and tags

The roles and their tags keep their names.

| Role | What changed |
|---|---|
| `workspace` | It installs the pinned release of `nucleate` and `nucleated` for the agent user, with the checksum verified, in place of the Python script. It creates the nucleus with `nucleate init` and adds each repository with `nucleate clone`. |
| `agent_servers` | It installs one `agent-server@<name>.service` per entry in `environments`, under a shared memory cap (`agents.slice`), in place of the single `nucleated.service` supervisor. Each server still runs inside tmux, now in a tmux server of its own. |
| `claude` | It writes one `settings.json` per login, with `nucleated hook` registered in place of `notify.sh`. |
| `day2` | It installs `nucleated`, its configuration and its unit, and signs the box in to Watch. It keeps the weekly disk cleanup of container images, the pnpm store and the journal, and the nightly backup. The refresh, snapshot and heartbeat timers are gone. |

### On the box

| Before | Now |
|---|---|
| `~/.local/bin/nucleate`, a Python script, with its MCP server in a virtual environment | `~/.local/bin/nucleate`, the Rust binary. Sessions see each repository under its GitHub name (`your-org/web`), not `workspace/web`. |
| `nucleated.service`, a tmux supervisor for the Remote Control server, started by `~/bin/start-agents` | `agent-server@main.service`, one per environment, running `~/.local/bin/agent-server`. Look at a server with `tmux -L agent-main attach`. |
| `heartbeat.timer` and `~/.local/bin/heartbeat` | `nucleated.service`, the daemon. |
| `nucleate-refresh.timer` | `nucleated`'s `refresh` job. |
| `wip-snapshot.timer` and `~/.local/bin/wip-snapshot` | `nucleated`'s `snapshot` job. |
| The worktree half of `agent-gc` | `nucleated`'s `cleanup` job. |
| `~/.claude/hooks/notify.sh` and `push-token` | `nucleated hook`, registered in each login's `settings.json`. |

### A box built with an earlier copy of the recipe

Run `ansible-playbook site.yml` once, at a quiet moment. The playbook stops
and removes the timers, scripts and tokens in the left-hand column above, and
replaces the old `nucleated.service`. Replacing it stops the tmux session
that unit supervised, which ends the sessions running in it. Then start each
agent server under its new unit:

```bash
systemctl --user start agent-server@main.service
```

The work in those sessions is not lost: session folders stay in the nucleus
until everything in them is pushed.
