# MyBudget

Flask personal finance tracker backed by a local SQLite database. No database server is needed.

## Run

Install the app dependencies from the repository root:

```powershell
python -m pip install -r personal_expense_ttracker\requirements.txt
python personal_expense_ttracker\app.py
```

The app creates `personal_expense_ttracker/mybudget.sqlite3` and its tables automatically on first request. Set `DATABASE_PATH` to store the database elsewhere, and set a stable random `SECRET_KEY` so login sessions remain valid after restarts. Enable secure cookies behind HTTPS with `COOKIE_SECURE=1`.

To reset local data, stop the app and delete `mybudget.sqlite3`. Existing records in the old MySQL tables are not imported.

Each account gets private default categories. Transaction and budget operations are scoped to the logged-in user, with SQLite foreign keys enforcing category ownership.

## GitHub and Vercel

The root `app.py` and `requirements.txt` let Vercel detect the Flask app without a `vercel.json`. Set a stable `SECRET_KEY` in Vercel project environment variables and enable `COOKIE_SECURE=1` for production HTTPS.

**Before using Vercel for real accounts, replace local SQLite with a persistent hosted database.** Vercel Functions do not provide shared persistent local file storage, so the ignored `mybudget.sqlite3` is only for local development; Vercel cannot safely store account data in it. The ignore files keep local databases, secrets, and Python cache files out of Git and deployment uploads.
