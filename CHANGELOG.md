# Changelog

Every change to the settings in `group_vars/all.yml` and `inventory.ini` is
listed here, because the installer at `nucarium.sh` and your own copy of those
two files both depend on their names.

## Session names in Watch

This entry has no version number of its own: the release that carries it is
numbered when it is published.

Watch can show each session by its name, as the agent or the tool that runs it
has it, in place of its short id. A box sends names only when its settings say
so.

### Settings added

| Setting | Default | What it is |
|---|---|---|
| `watch_session_names` | `false` | Whether each session's name is sent to Watch. `true` writes `session_names = true` into `nucleated`'s configuration and into the configuration its hook reads in a container; `false` writes nothing, and no name is read on the box or sent. `true` needs a `nucleated` that knows the setting: an older one refuses its configuration. |

No setting is renamed or removed, and a settings file without it works as it
is.

### Roles and tags

| Role | What changed |
|---|---|
| `day2` | Writes `session_names = true` into both of `nucleated`'s configurations when `watch_session_names` is true. |

### A box built with an earlier copy of the recipe

Nothing to do: the setting is off unless you turn it on. To turn it on, set
`watch_session_names: true` and run `ansible-playbook site.yml --tags day2`.

## A spool per container, and a proxy that never reaches the box

This entry has no version number of its own: the release that carries it is
numbered when it is published.

Two changes to every box with a container environment. Each container
writes a spool folder of its own, so no container can read or write
another's waiting events. And no environment's proxy connects to the box
itself, in any network mode, `full` included: not to an address on the
box's interfaces (its tailnet and LAN addresses), its gateways, loopback,
link-local addresses or Tailscale's resolver, and not to a name that
resolves to one. A box with no container environment is unchanged.

### Settings changed

No key is added, renamed or removed.

| Setting | What changed |
|---|---|
| `nucleate_version` | A container environment needs `nucleate` 0.14.0 or later, the first whose `nucleated` reads each container's own spool folder. The playbook asks the box's `nucleated`, and stops on an older one before it changes any container's unit. |

### Roles and tags

| Role | What changed |
|---|---|
| `agent_servers` | Makes `~/.local/state/nucleated/spools/<name>/` (the agent user's, mode 700) for each container environment and mounts it in its container where the shared spool was. A container keeps the shared one until it next starts, and `nucleated` reads both. Stops first when the box's `nucleated` does not read them. |
| `env_runtime` | Writes the box's addresses, from its network facts read during the run, to `box.json` beside each proxy's rules in `/etc/nucarium/proxy/<name>/`, root's. The proxy reads it again when it changes. It looks a name up once, as it connects, refuses it when any of its addresses is the box's, and otherwise connects to the address it found. It refuses everything while `box.json` cannot be read. The proxy image is built again. A new LAN address takes effect at the next run of the role; it builds no environment image. |

## Logins and setups

This entry has no version number of its own: the release that carries it is
numbered when it is published.

A box with several Claude logins and several kinds of work can list them
apart, as `logins` and `setups`, in place of `environments`. Each login
names the setups it joins, and the playbook makes one environment for each,
named `<setup>-<login>`, with the setup's keys, the login's capacity and
the config folder `/home/agent/.claude-<setup>-<login>`. A box without
`setups` works exactly as before.

### Settings added

| Setting | Default | What it is |
|---|---|---|
| `setups` | none | A list of setups. Each has a `name` (lower-case letters, digits and hyphens) and any of the keys an environment takes except `name`, `config_dir` and `capacity`: `runtime`, `network`, `allowed_hosts`, `variables`, `setup_script`, `repos`, `secret_variables`, `github`, `start_script`. Needs `logins`. |
| `logins` | none | A list of logins. Each has a `name`, an optional `capacity`, and `setups`, the setups it joins (at least one, each once). Needs `setups`. Delete the `environments:` block when you add these: the playbook stops while `environments` is anything other than the shipped `main` entry. |
| `setup_secrets` | none | The values of each setup's `secret_variables`, as `setup_secrets.<setup>.<NAME>`, in your file of environment secrets (`-e @environment-secrets.yml`), or as `secrets.setups.<setup>.<NAME>` in a whole `secrets` given with `-e`; `setup_secrets` wins where both name one. Every environment of the setup gets them. With setups, `environment_secrets` and `secrets.environments` are not read, and the playbook stops while they hold values. |

Each pair is a whole environment: its own agent server, container, nucleus,
Watch environment and sign-in. The pairs of a setup with `github` share one
commit-signing key, the setup's, made once on the box in
`/etc/nucarium/setups/<setup>/` (root's, and out of reach of sandboxed
commands on the host) and copied into each pair's folder on every run. The
playbook copies its public half to `out/<box>-<setup>-signing.pub`, and the
closing message asks for it to be registered once. A setup whose pairs no
longer have `github` loses its key.

### Settings changed

| Setting | What changed |
|---|---|
| `environments` | An environment's `name` may be at most 48 characters: its proxy's host name, `nucarium-proxy-<name>`, must fit in one 63-character DNS label. The playbook stops on a longer one. |

### Roles and tags

| Role | What changed |
|---|---|
| `env_runtime` | Makes each setup's signing key, copies it into its pairs' folders, fetches its public half once, and removes the keys of setups that no longer have `github`. |
| `claude` | Sandboxed commands on the host may not read `/etc/nucarium/setups`. |

The playbook makes the environments of logins and setups before anything
else, on every run, `--tags` runs included.

### A box built with an earlier copy of the recipe

Nothing to do. To move a box to logins and setups, replace its
`environments:` block with `setups:` and `logins:` and run the whole
playbook. The environments that leave the list are removed as they always
are, when their servers are idle; each new pair needs one sign-in by hand,
listed in the closing message.

## Watch's actions on leftover session folders

This entry has no version number of its own: the release that carries it is
numbered when it is published.

Watch lists the session folders a box keeps, with **Push** and **Clean up**
on each. A box runs them only when its settings say so.

### Settings added

| Setting | Default | What it is |
|---|---|---|
| `watch_worktree_actions` | `false` | Whether the box does what Watch asks with a leftover session folder: Push, and Clean up. `true` writes `worktree_actions = true` into `nucleated`'s configuration; `false` writes nothing, and the box refuses every such action. `true` needs a `nucleated` that knows the setting: an older one refuses its configuration. |

No setting is renamed or removed, and a settings file without it works as it
is.

### Roles and tags

| Role | What changed |
|---|---|
| `day2` | Writes `worktree_actions = true` into `nucleated`'s configuration when `watch_worktree_actions` is true. |

### A box built with an earlier copy of the recipe

Nothing to do: the setting is off unless you turn it on. To turn it on, set
`watch_worktree_actions: true` and run `ansible-playbook site.yml --tags day2`.

## Environments in their own container

This entry has no version number of its own: the release that carries it is
numbered when it is published.

`runtime: container` now does what it says: the environment's agent server
and every session it starts run in a rootless Podman container of the
environment's own, as root on Ubuntu 24.04 with what a Claude Code cloud
session has. Its setup script is built into the container's image once, as
a cloud environment's is, and its network goes through its own proxy. It
works in a nucleus of its own, `~agent/workspace-<name>`, with its own
clones of the repositories, so nothing its sessions write reaches the
sessions of another environment or what the host's agent servers read. An
environment on the host runs exactly as before.

### Settings changed

No key is added, renamed or removed.

| Setting | What changed |
|---|---|
| `runtime` | `container` runs the environment in its container (it used to build the base image only). It needs a `config_dir` of the environment's own, directly in the agent user's home and named `.claude-<something>`, shared with no other environment: left out, `~/.claude` or anything else, the playbook stops and says so. A container can write its login's folder (its MCP servers and hooks), so a `config_dir` that has been a container environment's is never used on the host again: the playbook refuses `runtime: host` for it, and an environment moved back needs a new `config_dir` and a new sign-in (the record is in `/etc/nucarium/container-logins/`, root's). It also needs `nucleate_version` at `nucleate_minimum_for_containers` (in `vars/runtime.yml`, 0.7.0 for now) or later, the first release in which `nucleate` and `nucleated` check a repository's git config, and run no hook, before they run git there; the playbook stops on an older one, and writes `vetting = "enforce"` under `[git]` in `nucleated`'s configuration on a box with a container environment. Switching takes effect when the environment's agent server next stops by itself (after about ten minutes with no session) or when you restart it, never mid-session, and the box never runs two servers for one login. |

### Roles and tags

| Role | What changed |
|---|---|
| `env_runtime` | Now runs before `env_setup`. Also installs the image builder for container environments (`~/.local/bin/nucarium-env-build`, with the agent user's units `nucarium-env-build@<name>` and `nucarium-env-check@<name>`), and writes the box's Git identity, commit signing (a copy of the box's signing key) and GitHub credential helper, and the packages token, root's, in `/etc/nucarium/box/`, which every container mounts read-only. |
| `env_setup` | Writes each environment's `runtime` beside its variables, and for a container environment its base image (`image.env`), its proxy's variables (`network.env`), the `nucleate` configuration for its own nucleus (`nucleate.toml`) and the repositories it offers (`repos`), all of which its container reads. `nucarium-env-setup@<name>` runs for every container environment, script or not: it builds `localhost/nucarium-env-<name>:<hash>` from the base image, the script, the variables and the network, in the agent user's own manager, tags it `:current`, and records the build in `<name>.setup.json` as before. A boot with nothing changed builds nothing; a failed build keeps the previous image. |
| `agent_servers` | A quadlet unit per container environment, root's, in `/etc/containers/systemd/users/<uid>/agent-env-<name>.container`, giving `agent-env-<name>.service` in `agents.slice`. `agent-server@.service` conflicts with it, starts only while its environment is on the host, and hands over to it when it stops; the playbook enables the unit of each environment's runtime and disables the other without stopping it. The helpers both run are root's, in `/usr/local/lib/nucarium/`. Each container's server runs in `/etc/nucarium/servers/<name>/`, so the Claude app names it after its environment. A container mounts only its environment's own nucleus, never the shared one, and writes it, but not its `.claude/` (with the worktree hooks), `.mcp.json`, `AGENTS.md`, `CLAUDE.md`, `.seeds/` or any repository's `hooks/`, which are mounted read-only; the container does not start while one of the first five is missing, a link, or not a folder or file as it should be. The bare repositories' `config` stays writable, and the host's `nucleate` and `nucleated` check it before they run git there. A repository added to `repos` later is cloned by the container's agent server, inside the container, at its next start. A container registers nucleate's MCP server for its own login, inside itself, at every start; the playbook never runs `claude` on the host with a container's login. |
| `claude` | The session-environment hook moved from `~/.claude/hooks/session-env.sh`, which the agent user could rewrite, to `/usr/local/lib/nucarium/session-env.sh`, root's, for every environment; the old copy is removed. A container environment's settings turn Claude Code's sandbox off, the container being the boundary, and name `nucleated` by its full path. |
| `day2` | `nucleated`'s configuration names `agent-env-<name>.service` as a container environment's unit. A tokenless copy of the environments for the hook inside containers, `~/.config/nucleated-hook/config.toml`. With a container environment, `[git] vetting = "enforce"`. `agent-gc` also removes the environments' image tags that nothing uses: of the base image and of each container environment's, all but the one `:current` names, and every tag of an environment no longer in a container. |
| `workspace` | Makes each container environment's own nucleus, `~/workspace-<name>`, with `nucleate init` and `nucleate clone` on the host, only while it is new (before any container has run there); after that the host runs no git in it but `nucleated`'s. Gives it its `.claude/`, `.seeds/`, empty `AGENTS.md`, `CLAUDE.md` and `.mcp.json` where there are none, and `AGENTS.md` from `agent-context/`, written in place so a running container's read-only mount stays on it. Registers nucleate's MCP server for the logins on the host only. The shared nucleus is unchanged. |
| `toolchain` | The GitHub credential helper is the one shared with the containers; its value is unchanged. |

### A box built with an earlier copy of the recipe

Nothing to do for an environment on the host. The next run moves the
session hook to `/usr/local/lib/nucarium/` and rewrites each login's
settings to name it.

To move an environment into its container, give it its own `config_dir`
(`/home/agent/.claude-<name>`) if it has none, set `runtime: container` and run `ansible-playbook site.yml
--tags env_runtime,env_setup,claude,workspace,agent_servers,day2`. Then sign
it in by hand, once, as the closing message says:

```bash
systemctl --user start agent-env-<name>.service
podman exec -it agent-env-<name> claude                         # sign in, trust the folder, /mcp, /exit
podman exec -it agent-env-<name> tmux -L agent-<name> attach    # answer y to enable Remote Control
```

The first login (`~/.claude`) stays on the host. To move it too, make a new
`config_dir` for it from a copy of `~/.claude` and `~/.claude.json` first.

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
