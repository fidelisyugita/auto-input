# Bot core (bundled for Docker)

Copy of the parent project bot files used inside the container.
Update from repo root when the main bot changes:

```bash
cp ../bot.py ../captcha_solver.py ../nik_store.py ../config.py .
```

`browser_setup.py` is overridden at build time from `bot_worker/browser_setup.py` (Linux/Docker).
