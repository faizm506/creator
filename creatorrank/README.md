# CreatorRank

Django site where Instagram creators and brands sign up, get ranked on a public leaderboard, and
connect through campaigns. Creators can boost their profile by paying you directly via UPI.

## Run in GitHub Codespaces
1. Create a new GitHub repo, upload this folder's contents (or push them), then **Code → Codespaces → Create codespace**.
2. Wait for setup. It installs packages, runs migrations and loads demo creators.
3. Edit `.env`: set `UPI_ID` and `UPI_NAME` to your own, and change `SECRET_KEY`.
4. Create your admin login: `python manage.py createsuperuser`
5. Start: `python manage.py runserver 0.0.0.0:8000` and open the forwarded port 8000.

Run tests: `python manage.py test`

## How boosting works (no payment gateway)
1. Creator opens **Settings → Boost**, picks a plan, scans the QR (or taps "Open UPI app") and pays you.
2. They enter the 12-digit UPI reference (UTR) from their receipt.
3. You open `/admin/` → **Boost requests**, check the UTR in your bank/UPI app, select the row and
   run **Approve selected**. The boost starts (or extends) automatically. Use **Reject** if no payment is found.

Prices live in `config/settings.py` (`BOOST_PLANS`). The amount is always taken from the server, never the browser.

## Security included
- Passwords hashed by Django, validators on, CSRF on every form, sessions HttpOnly + SameSite.
- Rate limits on sign-in, sign-up, boost and apply (per IP/user).
- Duplicate UTRs rejected, max 3 pending boost requests per user, approval inside a DB transaction.
- WhatsApp numbers shown only to signed-in members and only if the creator opts in.
- No inline scripts or styles, so a strict Content-Security-Policy can be added later.
- With `DEBUG=False`: forced HTTPS, secure cookies, HSTS. Set a long `SECRET_KEY`, and set `ADMIN_URL` to a private path.

## Before going live
- Delete demo data (admin → Profiles → delete the `*.example.com` users).
- Move from SQLite to Postgres and use a shared cache (Redis) if you run more than one server process.
- Deploy with `gunicorn config.wsgi` and `python manage.py collectstatic` (WhiteNoise serves static files).
- Follower counts are self-reported. Use the `verified` checkbox in admin after you check a creator's Instagram.
- Add a Privacy Policy and Terms page (you collect emails).
