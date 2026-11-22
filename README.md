# The Nucarium box recipe

An Ansible playbook that turns a mini PC with a fresh Ubuntu Server install
into a Nucarium box: a hardened, encrypted, UPS-aware machine that runs coding
agents around the clock. You start sessions on it from your phone or laptop
and walk away.

It runs from your own Mac or Linux workstation, over SSH. It holds no secrets:
the settings file has 1Password references, which are read on your
workstation when a playbook runs (see [Secrets](#secrets)).

This recipe has been syntax-checked and linted, and its templates rendered and
read, but it has not been run end to end on real hardware.

## What it builds

- **Three users.** You administer the box. Agents run as `agent`, which has
  no `sudo` and none of your credentials. A service-only user, `broker`,
  holds the long-lived secrets and hands the agents short-lived tokens, so an
  agent can use a one-hour GitHub token but never read the key that mints it.
- **An encrypted disk that unlocks by itself.** The TPM holds the disk key, so
  the box restarts unattended after a power cut. The passphrase still works.
- **Tailscale only.** The firewall admits your tailnet and, as a fallback, SSH
  from your own network. The box is tagged so it cannot open connections to
  your other devices.
- **A clean shutdown on low battery.** NUT watches the UPS, shuts the box down
  and power-cycles the outlets so the box starts again when power returns.
- **The nucleus.** `~agent/workspace` holds bare clones of your repositories
  in `.repos/`, one folder per session in `.worktrees/`, and seed files in
  `.seeds/`. [`nucleate`](https://github.com/nucarium/nucarium-cli) manages it:
  each session starts empty and adds the repositories it needs as git
  worktrees, and a session's folder is removed only when nothing in it is
  unsaved.
- **Agent servers.** One Claude Code Remote Control server per environment
  (a Claude login), each a systemd user service that waits for the network
  and restarts itself.
  Every command an agent runs is confined by Claude Code's sandbox.
- **A session that feels like a cloud session.** Agents find what a Claude
  Code cloud session gives them, in the same places: Playwright's Chromium
  in `/opt/pw-browsers` with its system libraries, Chrome for Testing at
  `/usr/bin/google-chrome`, `PLAYWRIGHT_BROWSERS_PATH`, `CHROME_PATH` and
  `PUPPETEER_EXECUTABLE_PATH` set, Node under `/opt/node22` and
  `/opt/node24`, Python with pip, uv, poetry, ruff, black, mypy and pytest,
  Rust, Java 21 with Maven and Gradle, clang, cmake, ninja and conan,
  `docker` and `docker compose` (on Podman), PostgreSQL and Redis (installed,
  not started), yq, tmux, vim and nano. They reach every host a cloud
  session reaches by default, plus `sandbox_extra_allowed_domains`.
  Commands may write only where `vars/sandbox.yml` says: the nucleus (the
  bare repositories in `~/workspace/.repos/` included), the package and
  build caches (`~/.cache`, `~/.npm`, pnpm's store and lock folders, `~/go`,
  `~/.cargo`, `~/.rustup`, `~/.m2`, `~/.gradle`), `/tmp` and `/var/tmp`.
  Everything else in the home stays read-only, every dotfile included, and so
  do `~/go/bin`, `~/.cargo/bin` and each bare repository's `hooks/` and
  `config`, because a change to any of them would
  reach a program that runs outside the sandbox. Two things still differ
  from a cloud session: agents are not root, so they cannot install system
  packages or start PostgreSQL and Redis themselves, and the box runs the
  Ubuntu release it was installed with.
- **`nucleated`, the box daemon.** One service that sends a heartbeat, records
  when a session starts, works, needs you, stops or fails, fetches the
  repositories, removes finished sessions, and saves uncommitted work to a
  hidden ref on GitHub.
- **Nucarium Watch, if you want it.** `nucleated` reports to
  [Nucarium Watch](https://nucarium.com), which tells you the moment an agent
  needs you or the box goes dark. Watch sees which agent is doing what, where
  and since when, never what it was told or what it wrote. With Watch off,
  nothing leaves the box and `nucleated status` shows the same view locally.
- **A voice of its own when Watch is silent, if you want it.** Give the box
  an address of yours and it posts there itself when it cannot reach Watch,
  and for each session that starts waiting for you meanwhile.

## What you need

| | |
|---|---|
| **Hardware** | An x86_64 mini PC with a TPM and Secure Boot. The reference build is an ASUS NUC 16 Pro with 64 GB of memory and a 2 TB NVMe SSD, on a USB-connected UPS. A virtual machine works with `nut_enabled: false`. |
| **On the box** | Ubuntu Server 26.04 LTS, installed with an encrypted disk. `autoinstall.yml` writes the answers for an unattended install. |
| **On your workstation** | Ansible, the 1Password CLI (`op`), signed in, and an SSH key. |
| **Accounts** | A Claude subscription that includes Remote Control, a Tailscale tailnet, a GitHub organisation where you can create a GitHub App, and 1Password. A Nucarium Watch account is optional. |

The guide at [nucarium.dev](https://nucarium.dev) walks through the hardware,
the BIOS, the accounts and the tests. This README covers the playbook.

## Getting the recipe

The installer fetches a release of this recipe, checks your tools and fills in
the two settings files with you:

```bash
curl -fsSL https://nucarium.sh | sh
```

Or clone it and do the same by hand:

```bash
git clone https://github.com/nucarium/nucarium-ansible.git
```

On a Mac, the tools are:

```bash
brew install ansible 1password-cli
```

On Linux, install Ansible with `pipx install --include-deps ansible` and the
1Password CLI from 1Password's own instructions. Then, in the recipe's
folder:

```bash
ansible-galaxy collection install -r requirements.yml
```

`autoinstall.yml` also needs `passlib`, to hash your login password. Install
it into the same Python that Ansible uses: on a Mac,
`"$(brew --prefix ansible)/libexec/bin/python" -m pip install passlib`; with
pipx, `pipx inject ansible passlib`.

## The order of work

1. **Prepare.** Create the Tailscale tag and auth key, the GitHub App and the
   packages token, and save the secrets in 1Password. The guide has each step.
2. **Fill in the settings.** `inventory.ini` names the box and its address.
   `group_vars/all.yml` holds everything else, with a comment on every
   setting. Sign in to 1Password (`op signin`) before running anything.
3. **Install Ubuntu.** `ansible-playbook autoinstall.yml` writes
   `out/cidata/`, the answers for an unattended install, to put on a second
   USB stick. `out/` holds secrets; it is ignored by git, and the guide says
   when to wipe it.
4. **Build the box.** `ansible-playbook site.yml`. Stay near the box's screen
   the first time: partway through, the playbook reboots it to prove the disk
   unlocks by itself.
5. **Do the manual steps** the playbook prints at the end (below).
6. **Test it**: a session from your phone, and the power-cut test in the
   guide.

## What each role does

Roles run in this order. Each has a tag of the same name.

| Role | Does |
|---|---|
| `base` | Updates, packages, time zone, no sleep, automatic security updates, file-watcher limits, TRIM through the encryption layer, Ubuntu Pro and Livepatch |
| `tpm` | Binds the disk key to the TPM, saves a disk-header backup to `out/` on your workstation, sets the boot-menu password, and reboots to prove the unattended unlock |
| `network` | Tailscale (tagged), SSH hardening, firewall |
| `nut` | UPS monitoring and the low-battery shutdown. Skipped when `nut_enabled` is false |
| `users` | The `agent` and `broker` users, the short-lived token folder, and the sandbox check: a bwrap inside a bwrap as the agent user, as Claude Code's sandbox runs. If AppArmor blocks it, installs the recipe's own bwrap profile in place of Ubuntu's `bwrap-userns-restrict` and checks again |
| `toolchain` | GitHub CLI, Terraform if used, Go, Node, pnpm, the commit-signing key and Git identity |
| `cloud_parity` | What a Claude Code cloud session has: Playwright's Chromium (for `playwright_version`) and its system libraries in `/opt/pw-browsers`, Chrome for Testing, Node under `/opt`, the Python tools, Rust, Java with Maven and Gradle, the C/C++ tools, `docker` on Podman, PostgreSQL and Redis, the cloud session's variables for login shells, and pnpm's lock folders at every login |
| `broker` | The GitHub App key and the timer that mints a fresh GitHub token every 20 minutes; the HCP Terraform token if used |
| `claude` | Claude Code and, for each login, its settings file: sandbox (required, with no unsandboxed retry, and the paths it may write), update channel, deny rules, the GitHub token hook and the `nucleated hook` entries. Also your `agent-context/` files |
| `workspace` | Downloads the pinned release of `nucleate` and `nucleated`, verifies its SHA-256, and installs both for the agent user. Creates the nucleus with `nucleate init`, makes each repository available with `nucleate clone`, and registers the worktree hooks and the `nucleate` MCP server |
| `agent_servers` | One `agent-server@<name>.service` per entry in `environments`, under one shared memory cap. Enabled, not started |
| `day2` | `nucleated`: its configuration, generated from `environments`, the UPS's name and `box_notify_url`, its unit, and the sign-in to Nucarium Watch if you gave a token. Also the two jobs the daemon does not own: a weekly cleanup of container images, the pnpm store and the journal, and the nightly encrypted backup if configured |

## Reporting to Nucarium Watch

`watch_target` in `group_vars/all.yml` is `hosted` or `none`: Watch, or
nowhere. The box signs in with a machine token, which can only write that one
machine's reports and can read nothing. There are two ways to give it one.

**With you present.** Leave `secret_refs.watch_machine_token` empty. The
playbook ends by telling you to run this on the box, as `agent`:

```bash
nucleate login
```

It prints a short code, the address `https://app.nucarium.com/activate` and a
link that already carries the code, then waits. Open either on your phone or
laptop, sign in, choose the machine or name a new one, and approve. The box
says what was granted and appears in Watch within a minute.

**With nobody present.** Mint a machine token in the Watch console, save it in
1Password, and put its reference in `secret_refs.watch_machine_token`. The
playbook first asks the box, with `nucleate whoami`, whether it is already
signed in. Only if it is not, or Watch rejects the token it has, does the
playbook read the token on your workstation and pipe it to
`nucleate login --token-stdin` on the box. On the way the token is never a
command argument, never in the log and never in a file; `nucleate` stores it
in `~agent/.config/nucleated/token`, which only the agent user can read. The
playbook then asks `nucleate whoami` again and stops if Watch rejects the
token.

To rotate a token: mint a new one, update the 1Password item, revoke the old
one in the Watch console, and run `ansible-playbook site.yml --tags day2`.

### When Watch cannot be reached

If Watch itself cannot be reached, nothing tells you that an agent is waiting.
Set `box_notify_url` in `group_vars/all.yml` to an address of your own and the
box tells you itself. It posts there:

- once when no heartbeat has been accepted for ten minutes;
- once for each session that starts waiting for you while that lasts;
- once when Watch accepts a heartbeat again.

Each post carries the box's name, the environment's name and a time, nothing
else, and goes to that address only, never to Nucarium. The address takes the
same request as an alert destination in Watch, so a push topic such as
`https://ntfy.sh/<your-topic>` works as it is. It must start with `https://`
(`http://` only for a service on the box itself) and hold no username or
password. If it needs a token, save the token in 1Password and put its
reference in `secret_refs.box_notify_token`: the playbook stores it in
`~agent/.config/nucleated/notify-token`, which only the agent user can read,
and the box sends it as a bearer token.

The box posts only while `watch_target` is `hosted` and it is signed in. This
covers Watch being unreachable. It does not cover a box with no network at
all: that box cannot reach your address either, and Watch tells you it has
gone dark.

On a box with a UPS, the playbook also gives `nucleated` the UPS's name, so
its heartbeat says when the box is running on battery. `nucleated` asks NUT,
which answers any user on the box without a password.

## What is still a manual step, and why

The playbook prints these, filled in for your box, when it finishes.

| Step | Why it is not automated |
|---|---|
| Hardware, BIOS settings, booting the installer, typing the disk passphrase once | They happen at the box, before there is anything to connect to. |
| Registering the agents' signing key on GitHub | It uses your own GitHub sign-in, which never goes on the box. |
| Signing each agent server in to Claude, and authorising connectors with `/mcp` | Each is a sign-in in your browser. |
| Starting each agent server once by hand | The first start asks whether to trust the folder and to enable Remote Control, and waits for you to answer in a terminal. |
| `nucleate login`, unless you gave a token | Approving a box is your decision, made in the Watch console. |
| Attaching the disk-header backup to the passphrase in your password manager, then deleting it | The file must end up somewhere only you can reach. |
| The power-cut test | Someone has to pull the plug. |

## Running it again, or one part of it

Re-running `site.yml` is safe: it only changes what differs. To change
anything on the box, edit the settings or the files here and run it again.
Don't edit the installed copies on the box; the next run overwrites them.

```bash
ansible-playbook site.yml --check --diff     # show what would change
ansible-playbook site.yml --tags workspace   # one role
ansible-playbook site.yml --tags claude,day2
```

| To | Change | Then run |
|---|---|---|
| Make another repository available | `repos` (and the GitHub App's selected repositories) | `--tags workspace` |
| Allow agents another website | `sandbox_extra_allowed_domains` | `--tags claude` |
| Follow a repository to another Playwright | `playwright_version` | `--tags cloud_parity` |
| Add a second Claude login | `environments` | `--tags claude,workspace,agent_servers,day2`, then sign it in and start it by hand |
| Change an environment's capacity or the memory cap | `environments`, `agents_memory_*` | `--tags agent_servers`, then restart that server |
| Upgrade `nucleate` and `nucleated` | `nucleate_version` and `nucleate_sha256` | `--tags workspace` |
| Turn Watch on or off, or rotate its token | `watch_target`, the 1Password item | `--tags day2` |
| Set, change or remove the box's own notifier | `box_notify_url`, the 1Password item | `--tags day2` |
| Renew the packages token | the 1Password item | `--tags toolchain` |

The playbook never restarts an agent server, because that ends its sessions.
Do it yourself at a quiet moment, as `agent` on the box:

```bash
systemctl --user restart agent-server@main.service
```

`nucleated` picks up a changed configuration or a new token by itself.

## On the box

As `agent`:

```bash
nucleated status                      # what Watch would show
nucleated check                       # is the daemon set up correctly
nucleate whoami                       # is the box signed in to Watch
systemctl --user status agent-server@main.service nucleated.service
tmux -L agent-main attach             # the server's own output; Ctrl+B then D leaves
journalctl --user -u nucleated -n 50
```

## Optional: `agent-context/`

If this folder exists beside the playbook, its contents are copied to the
agent user: `AGENTS.md` to the nucleus (`~/workspace/AGENTS.md`), `CLAUDE.md`
to each login's configuration folder, and `skills/` to each login's `skills/`.

## Secrets

Nothing secret is in this repository, and nothing secret should ever be
committed to your copy of it.

- **Where they come from.** Every secret is an item in your 1Password vault.
  `secret_refs` in `group_vars/all.yml` holds references to them
  (`op://vault/item/field`), which are safe to commit. A playbook reads the
  values on your workstation with `op read` as it runs, keeps them in memory,
  and never logs them.
- **What a playbook writes on your workstation.** Only `out/`, which git
  ignores: `out/cidata/` holds the unattended-install answers, with your
  password's hash and the disk passphrase in the clear, and
  `out/<box>-luks-header.img` is the disk-header backup. Wipe the first after
  the install and move the second into your password manager, as the guide
  and the playbook's closing message say.
- **Where they end up on the box.** The GitHub App key and the Terraform
  token belong to `broker` in `/etc/agent-broker`, mode 600. The backup
  credentials are root's, in `/etc/restic/env`. The packages token is in
  `~agent/.npmrc`, which is why it can only download. The Watch machine
  token is in `~agent/.config/nucleated/token`, written by `nucleate login`.
  The notifier's token, if you gave one, is beside it in `notify-token`,
  mode 600, and is left out of the nightly backup.

## Checking changes to the recipe

One script runs every check, and none of them needs a box:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
PATH="$PWD/.venv/bin:$PATH" scripts/check
```

It syntax-checks both playbooks, runs `ansible-lint`, `yamllint` and
`shellcheck`, and renders every template from the example settings into
`out/render/`, in two shapes, so you can read exactly what a box would
receive. It reads `nucleated`'s rendered configuration back as TOML and
checks it against the settings. The Build workflow (`.github/workflows/build.yml`) runs the same
script on every pull request and on `main`.

To run the linters and the commit-message check before each commit, install
[pre-commit](https://pre-commit.com) and run `pre-commit install` once.
Commit messages follow Conventional Commits (`type(scope): summary`).

## Assumptions

Choices this recipe makes where the product leaves room:

- **One organisation per box.** Every entry in `environments` shares the
  `agent` user, the nucleus, its repositories and one GitHub App.
  Environments on one box are not isolated from each other.
- **Ubuntu Server 26.04 LTS on x86_64.** Other distributions and arm64 boards
  are not covered.
- **1Password is the secret store.** Every secret is read with `op read` on
  your workstation.
- **One release archive holds both binaries.** `nucleate` and `nucleated`
  are released from `github.com/nucarium/nucarium-cli` as
  `nucleate-v<version>-x86_64-unknown-linux-musl.tar.gz`, with both at the
  archive's top level and its SHA-256 published beside it. `nucleate_sha256`
  must be that checksum; the playbook stops if it is not set. The
  repository's address is one variable, in `roles/workspace/vars/main.yml`.
- **The binaries belong to the agent user**, in `~agent/.local/bin`, where
  `nucleated`'s own unit expects them.
- **An agent server runs inside tmux.** Each environment's server has its
  own tmux server under `agent-server@<name>.service`, because Claude Code's
  Remote Control server is a terminal program: it asks its first-start
  questions in a terminal and shows its state there. The unit stops when the
  server exits and systemd starts it again, so the unit is active exactly
  while the server runs. Stopping the unit waits until the server and its
  sessions have exited, so a restart never starts a second server beside one
  that is still shutting down. `nucleated` reads the unit's state; it never starts
  or stops a server.
- **Hooks name their environment.** Each login's `settings.json` registers
  `nucleated hook <event> --env <name>`, so a session is always counted under
  the login that ran it, even though every environment shares one nucleus.
- **The token is stored only when needed.** `nucleate whoami` decides: a box
  that is signed in with a token Watch accepts is left alone.
- **Agents push with `git push origin HEAD`.** A bare repository's `config`
  is read-only to them, because `nucleated` runs git there outside the
  sandbox and a setting such as `core.fsmonitor` or `core.sshCommand` would
  run a command unconfined. So `git push -u` pushes but cannot record the
  upstream. Say so in your `agent-context/` files.
- **The weekly disk cleanup stays outside the daemon.** `nucleated` cleans up
  sessions; container images, the pnpm store and the journal are pruned by
  `agent-gc.timer`.

## Not covered

Running a second organisation's work in a virtual machine on the same box, and
rotating an HCP Terraform token on a schedule, are done by hand. The guide at
[nucarium.dev](https://nucarium.dev) describes both.

## Releases

Nobody tags a release by hand. A push to `main` runs semantic-release, which
reads the Conventional Commits since the last tag and creates the GitHub
Release and its tag: a `fix:` makes a patch release, a `feat:` a minor one,
and a push with neither makes none. Publishing the release packs the recipe
as `nucarium-box-<version>.tar.gz`, holding one folder of the same name, and
attaches it with its SHA-256. That archive is what the installer at
`nucarium.sh` downloads and checks.

Nobody copies a checksum by hand either. The two pins follow the releases:

| When | This happens | In |
|---|---|---|
| `nucarium-cli` publishes a release of `nucleate` | `nucleate_version` and `nucleate_sha256` in `group_vars/all.yml` move to it, in a commit `feat: nucleate <version>`, which releases the recipe | `pin-nucleate.yml`, here |
| This recipe publishes a release | The installer's repository is told the version and the archive's checksum, and moves the installer's pin | `package.yml`, here, then `pin-box.yml` in `nucarium/nucarium` |

Each side checks what it is told. `pin-nucleate.yml` downloads the Linux
archive the playbook installs and refuses the pin unless it hashes to the
checksum it was sent. It also refuses to move the pin backwards, and stops if
a version it already pins arrives with a different checksum.

All of it needs the Robot App's two secrets on the repository, `GH_APP_ID`
and `GH_PRIVATE_KEY`, and the App installed on `nucarium-cli` and `nucarium`
as well as here.

## Licence

Licensed under either of the [Apache License, Version 2.0](LICENSE-APACHE) or
the [MIT licence](LICENSE-MIT), at your option. Unless you state otherwise, any
contribution you submit for inclusion in this project is licensed the same way,
with no additional terms.
