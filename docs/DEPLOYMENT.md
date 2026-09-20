# Deployment

ripcale deploys with a **poll-based pull** model: your server reaches *out* to
GitHub, never the other way around. There is no CI that SSHes into the server,
no webhook, and no inbound port to expose.

A `systemd` timer runs `deploy/deploy.sh` every 5 minutes. The script does
`git pull --ff-only`, and only if the commit actually changed does it run
`docker compose up -d --build`. A no-op poll is essentially free.

```
you push  →  (≤5 min)  →  server pulls  →  rebuilds only if HEAD moved
```

## Prerequisites (on the server)

- Docker + Docker Compose installed.
- `git` installed.
- A non-root **deploy user** that is a member of the `docker` group:
  ```sh
  sudo useradd --create-home --shell /bin/bash deploy
  sudo usermod -aG docker deploy
  ```
- The repo cloned at a known path (below we use `/opt/ripcale-backend`).

## One-time server setup

1. **Clone the repo:**
   ```sh
   sudo mkdir -p /opt/ripcale-backend
   sudo chown deploy:deploy /opt/ripcale-backend
   # as the deploy user:
   git clone https://github.com/NatVIII/ripcale-backend.git /opt/ripcale-backend
   ```

2. **Create the gitignored config files** (they are not in the repo and persist
   across pulls):
   ```sh
   cd /opt/ripcale-backend
   cp .env.example .env                 # fill in RIPCALE_ADMIN_* (see README)
   cp config.example.yaml config.yaml   # adjust hosts/ports if needed
   cp intake.example.yaml intake.yaml   # your real sources
   ```
   Keep `data/` as-is (it's bind-mounted as a volume and holds the SQLite DB).

3. **Make the deploy script executable:**
   ```sh
   chmod +x /opt/ripcale-backend/deploy/deploy.sh
   ```

4. **Ensure `git pull` works from the server:**
   - **Public repo** — HTTPS clone/pull needs no auth; done.
   - **Private repo** — add a read-only deploy key to the repo
     (GitHub → Settings → Deploy keys) and configure it on the server, or use a
     fine-grained PAT via a credential helper.

## Enable the timer

Copy the bundled systemd units and start them:

```sh
sudo cp /opt/ripcale-backend/deploy/ripcale-deploy.service /etc/systemd/system/
sudo cp /opt/ripcale-backend/deploy/ripcale-deploy.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ripcale-deploy.timer
```

Edit `/etc/systemd/system/ripcale-deploy.service` first if your clone path or
deploy user differs from the defaults (`/opt/ripcale-backend`, `deploy`).

Check it's running:

```sh
systemctl status ripcale-deploy.timer
journalctl -u ripcale-deploy -n 50    # logs
```

The default interval is 5 minutes (`OnUnitActiveSec=5min`); tweak it in the
`.timer` unit if you want faster or slower polling.

### Cron alternative

If you prefer cron over systemd:

```sh
crontab -e
# add:
*/5 * * * * /opt/ripcale-backend/deploy/deploy.sh >> /opt/ripcale-backend/deploy/deploy.log 2>&1
```

## Day-to-day

- **Push and forget** — your commit goes live within ~5 minutes.
- **Deploy now (manual)** — run it yourself over SSH:
  ```sh
  ssh deploy@YOUR_SERVER '/opt/ripcale-backend/deploy/deploy.sh'
  ```

## Following a different branch

`deploy.sh` pulls the branch the clone is currently checked out on. To follow
`dev` (or any other branch):

```sh
# on the server
cd /opt/ripcale-backend
git checkout dev     # or: git fetch && git switch dev
```

## Troubleshooting

- **`git pull` fails** — usually auth (private repo) or the server's clone has
  diverged. `--ff-only` never merges, so if someone edited files on the server,
  the script fails loudly. Reset with `git reset --hard origin/main` if the
  server copy is meant to be a clean mirror (your `.env`/`config.yaml`/
  `intake.yaml` are gitignored, so they won't be touched).
- **Docker permission denied** — the deploy user isn't in the `docker` group
  (log out/in or use `newgrp docker`).
- **No rebuild happening** — confirm `git rev-parse HEAD` changes on the server
  after a push, and check `journalctl -u ripcale-deploy`.
- **Ports / access** — the admin app is loopback-only (`127.0.0.1:8082`); reach
  it over SSH tunnel if you're not on the box.
