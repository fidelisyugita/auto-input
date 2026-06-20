# MAP Automation — Oracle Cloud / Docker deployment

Web control panel to **start/stop** the MAP Catat Penjualan bot on your Oracle Ubuntu server.

The original CLI app in the parent folder is **unchanged**. This folder is a separate Docker deployment.

## What you get

- Browser URL to login, start, and stop the bot
- Upload `nik.json` from the web UI
- Set MAP merchant phone/email + PIN in the dashboard
- Headless Playwright (no display needed on the server)
- Data persisted in a Docker volume (`progress`, logs, NIK file)

## Requirements (Oracle VM)

- Ubuntu 22.04+ (or similar)
- Docker + Docker Compose
- **2 GB+ RAM** recommended (Chromium + OpenCV captcha solver)
- Outbound HTTPS to `subsiditepatlpg.mypertamina.id`

## Quick deploy on Oracle

### 1. Copy project to server

Copy **only the `oracle-deploy` folder** — it is self-contained (includes the bot code in `bot_core/`):

```bash
# On your Mac — from repo root
scp -r oracle-deploy ubuntu@YOUR_ORACLE_IP:~/map-automation/
```

Or clone/pull on the server if you use git.

### 2. Configure environment

```bash
cd ~/map-automation/oracle-deploy
cp .env.example .env
nano .env
```

**Change these before going live:**

| Variable                  | Purpose                                    |
| ------------------------- | ------------------------------------------ |
| `WEB_USERNAME`            | Dashboard login                            |
| `WEB_PASSWORD`            | Dashboard password                         |
| `WEB_SECRET_KEY`          | Session cookie secret (long random string) |
| `MERCHANT_PHONE_OR_EMAIL` | Default MAP merchant (can change in UI)    |
| `MERCHANT_PIN`            | Default MAP PIN (can change in UI)         |
| `WEB_PORT`                | Host port (default `8081`)                 |

### 3. Open firewall (Oracle Cloud)

In **Oracle Cloud Console → Networking → Security List**:

- Ingress rule: TCP port `8081` (or your `WEB_PORT`) from your IP or `0.0.0.0/0`

On Ubuntu (if `ufw` is enabled):

```bash
sudo ufw allow 8081/tcp
```

### 4. Build and run

```bash
cd ~/map-automation/oracle-deploy
docker compose up -d --build
```

> **Note:** Use `docker compose` (v2) or `docker-compose` (v1) — both work.
> Build context is this folder only; no parent `bot.py` files needed.

### 5. Open in browser

```
http://YOUR_ORACLE_IP:8081
```

1. Login with `WEB_USERNAME` / `WEB_PASSWORD`
2. Enter MAP merchant credentials (or use defaults from `.env`)
3. Upload your `nik.json`
4. Click **Start bot**
5. Watch logs on the dashboard; click **Stop bot** anytime

## Useful commands

```bash
# Logs
docker compose logs -f

# Restart
docker compose restart

# Stop
docker compose down

# Rebuild after code changes
docker compose up -d --build
```

## Data persistence

All runtime data is stored in the Docker volume `map-data`:

- `/data/nik.json` — uploaded NIK list
- `/data/progress.json` — bot progress
- `/data/nik-filtered.json` — working + queue
- `/data/settings.json` — merchant settings from UI
- `/data/automation.log` — bot logs

```bash
# Inspect volume
docker volume inspect oracle-deploy_map-data
```

## HTTPS (recommended for production)

Put **Caddy** or **nginx** in front with TLS:

```
https://your-domain.com  →  http://localhost:8081
```

Do not expose the dashboard without HTTPS if it is on the public internet.

## Subscription / multi-user (later)

Current version supports **one dashboard login** and **one merchant** at a time.

For subscriber username/password per customer, you would add:

- Database per tenant (credentials, NIK, progress)
- Job queue (one bot per merchant)
- Admin panel to create accounts

The web UI is structured so merchant settings and NIK upload are already separate from the bot core.

## Troubleshooting

| Problem                     | Fix                                              |
| --------------------------- | ------------------------------------------------ |
| Container exits immediately | `docker compose logs` — check `.env`             |
| Captcha / browser errors    | Ensure `shm_size: 1gb` in compose (already set)  |
| Cannot access from browser  | Check Oracle Security List + `ufw`               |
| Bot won't start             | Upload NIK + set merchant phone/PIN in dashboard |
| `KeyError: 'ContainerConfig'` on `up` | Old docker-compose v1 bug — see below |

### `KeyError: 'ContainerConfig'` when running `docker-compose up`

Build succeeded but recreate failed — common with **docker-compose 1.29** + newer Docker.

```bash
cd ~/map-automation/oracle-deploy
docker-compose down --remove-orphans
docker rm -f map-automation 2>/dev/null || true
docker-compose up -d
```

Image is already built, so `--build` is not needed. If it still fails, use Docker Compose v2:

```bash
docker compose down
docker compose up -d
```

## Local test (before Oracle)

From the `oracle-deploy` folder:

```bash
cd oracle-deploy
cp .env.example .env
# edit .env

docker compose up --build
```

Open http://localhost:8081 (or whatever `WEB_PORT` you set)

## Syncing bot updates from parent project

`bot_core/` is a copy of the main bot files. After changing `bot.py`, `nik_store.py`, etc. in the parent folder, re-copy:

```bash
cp ../{bot.py,captcha_solver.py,nik_store.py,config.py} bot_core/
docker compose up -d --build
```
