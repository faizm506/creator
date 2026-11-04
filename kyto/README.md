# Kyto

Free creator and brand network for Ahmedabad: public leaderboard, reel showcases, direct hiring offers and in-app chat.
Built by [Zyrac](https://www.instagram.com/zyrac__/).

## Run in GitHub Codespaces
1. Upload this folder to a new GitHub repo, then Code → Codespaces → Create codespace.
2. Setup installs packages, creates the database and loads demo creators.
3. Open `.env` and paste your own `SECRET_KEY` (generate one below). Set `ADMIN_URL` to a private path.
4. `python manage.py createsuperuser`
5. `python manage.py runserver 0.0.0.0:8000`, then open port 8000.
6. `python manage.py test` runs the test suite.

Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```
Store it in a password manager. Never commit `.env`. On Codespaces you can also save it as a Codespaces secret named `SECRET_KEY`.
Changing the key signs everyone out, so keep one key for the life of the site.

## Upgrading from an older copy
```bash
python manage.py makemigrations core
python manage.py migrate
python manage.py recompute_scores
```

## Boost is switched off
Everything is free. The boost code stays in the project but is disabled (`BOOST_ENABLED=False`): the page returns 404,
no Featured shelf or badges show. To bring it back later, set `BOOST_ENABLED=True` and `UPI_ID` in `.env`.

## Going live (checklist)
- `DEBUG=False`, a long unique `SECRET_KEY`, `ALLOWED_HOSTS=yourdomain.com`, a private `ADMIN_URL`.
- Serve over HTTPS only. With DEBUG off the app forces HTTPS, secure cookies and HSTS.
- Set `TRUSTED_PROXY_COUNT=1` if you sit behind one proxy (Render, Railway, Nginx), so rate limits see real visitor IPs.
- Run `gunicorn config.wsgi --workers 1 --threads 8`. Rate limits are held in memory, so use one worker (or add Redis later).
- Add SMTP settings so password-reset emails really send.
- Delete the demo users (admin → Profiles, `*@example.com`). Move to Postgres and back up the database regularly.
- Keep packages updated (`pip install -U -r requirements.txt`, and enable the included Dependabot file).

## Security built in
Hashed passwords (10+ characters), CSRF on every form, HttpOnly + SameSite cookies, strict Content-Security-Policy,
clickjacking protection, per-account and per-IP sign-in lockout, throttled sign-up/reset/admin login/offers/messages,
owner-only access to offers and messages, contact details shared only after acceptance, Instagram embeds sandboxed
and loaded only when tapped, fixed-destination Instagram redirect (no open redirect), account deletion with password check.
