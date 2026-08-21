# TaskFlow

TaskFlow is a React/Vite frontend with a Django REST Framework backend and PostgreSQL persistence.

## Local setup

Prerequisites: Node.js 20+ and Python 3.12+.

```text
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
```

In another terminal:

```text
cd frontend
npm install
copy .env.example .env
npm run dev
```

## Environment variables

Backend `.env` requires `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `DATABASE_URL`. `DJANGO_LOG_LEVEL` and `SECURE_HSTS_SECONDS` are optional. Never commit `.env` files or real credentials.

Frontend builds require `VITE_API_BASE_URL`, including the `/api` suffix, such as `https://api.example.com/api`. The committed example uses localhost only for local development.

## Supabase PostgreSQL

Set `DATABASE_URL` to the Supabase connection string. PostgreSQL is selected whenever this variable is present and SSL is required. Without it, local development uses SQLite. Run Django migrations; do not manually modify the production schema.

## Backend deployment

Deploy `backend/` to a Python application host with:

```text
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn config.wsgi:application
```

Set `DJANGO_DEBUG=False`, a long random `DJANGO_SECRET_KEY`, the backend hostname in `DJANGO_ALLOWED_HOSTS`, the deployed frontend origin in `CORS_ALLOWED_ORIGINS`, and the Supabase `DATABASE_URL`. Serve the app behind HTTPS and configure the host's forwarded-proto header.

## Frontend deployment

Deploy `frontend/` to Vercel or equivalent:

```text
npm ci
npm run build
```

Set `VITE_API_BASE_URL` to the deployed Django API URL before building and publish `dist/`.

## Initial Admin

Create exactly the initial Admin through Django setup, never through registration:

```text
python manage.py createsuperuser
```

Run migrations in each environment before starting the backend. This project does not deploy automatically or modify hosted database data.

## Google sign-in setup

Google sign-in is optional and remains mediated by Django. Set these backend environment variables only in `backend/.env` or the hosting platform:

```text
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback/
FRONTEND_URL=http://localhost:5174
```

In Google Cloud Console, create an OAuth 2.0 Client ID with application type **Web application** and add this exact local authorized redirect URI:

```text
http://127.0.0.1:8000/api/auth/google/callback/
```

For production, use the exact HTTPS callback URL configured by the deployed Django host. Never expose `GOOGLE_CLIENT_SECRET` to the frontend or commit it.
