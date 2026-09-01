import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() == 'true'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is False.')
    SECRET_KEY = 'development-only-change-me'
# ALLOWED_HOSTS = [host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "taskboard-x6ef.onrender.com",
]
if os.getenv("ALLOWED_HOSTS"):
    ALLOWED_HOSTS += os.getenv("ALLOWED_HOSTS").split(",")

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'taskflow',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'

database_url_value = os.getenv('DATABASE_URL')
if not database_url_value:
    raise ImproperlyConfigured('DATABASE_URL must be set.')
database_url = urlparse(database_url_value)
if database_url.scheme not in ('postgresql', 'postgres') or not database_url.hostname or not database_url.path.strip('/'):
    raise ImproperlyConfigured('DATABASE_URL must be a valid PostgreSQL connection URL.')
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': database_url.path.lstrip('/'),
    'USER': database_url.username,
    'PASSWORD': database_url.password,
    'HOST': database_url.hostname,
    'PORT': database_url.port or 5432,
    'OPTIONS': {'sslmode': 'require'},
}}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
cors_allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS")

if cors_allowed_origins_env:
    CORS_ALLOWED_ORIGINS = [
        origin.strip()
        for origin in cors_allowed_origins_env.split(",")
        if origin.strip()
    ]
else:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://taskboard-puce-two.vercel.app",
    ]
# Only explicitly allowlisted origins may call the API. Origins come from the
# CORS_ALLOWED_ORIGINS env var (see .env.example); local development defaults
# are kept below for convenience. Never re-enable CORS_ALLOW_ALL_ORIGINS.
#
# CORS_ALLOW_CREDENTIALS is intentionally False: the API uses DRF
# TokenAuthentication via the Authorization header, so browsers never need to
# send cookies cross-origin.
CORS_ALLOW_CREDENTIALS = False
# django-cors-headers matches origins on exact scheme+host+port, and answers a
# preflight with 200 *without* any Access-Control-Allow-Origin when the origin
# is not matched. The browser then blocks the actual GET with a CORS error even
# though OPTIONS looked fine. Local dev servers (e.g. Vite) silently move to
# another free port when 5173 is taken, so allow any localhost/127.0.0.1 port;
# non-local origins still require an exact entry in CORS_ALLOWED_ORIGINS.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
]
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:8000/api/auth/google/callback/')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
GOOGLE_OAUTH_STATE_MAX_AGE = int(os.getenv('GOOGLE_OAUTH_STATE_MAX_AGE', '600'))
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@taskboard.local')
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'

# --- AI generation (server-side only; never exposed to the frontend) ---
# Google Gemini is the single AI provider. Keys are read in priority order:
# numbered GEMINI_API_KEY_1..4 first (blank values ignored); if none are set,
# the legacy single GEMINI_API_KEY (or its alias AI_API_KEY) is used. Keys are
# server-side only and are never exposed to the frontend, logs or responses.
def _gemini_api_keys():
    numbered = []
    for i in range(1, 5):
        value = os.getenv(f'GEMINI_API_KEY_{i}', '').strip()
        if value:
            numbered.append(value)
    if numbered:
        return numbered
    legacy = os.getenv('GEMINI_API_KEY', '').strip() or os.getenv('AI_API_KEY', '').strip()
    return [legacy] if legacy else []
GEMINI_API_KEYS = _gemini_api_keys()
# Backwards-compatible alias for the primary key (single-key setups).
AI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ''
# gemini-2.5-flash is no longer available to new Google AI keys; 3.6-flash is current.
AI_MODEL = os.getenv('AI_MODEL', 'gemini-3.6-flash')
# Ordered Gemini model fallback chain (server-side only). Comma-separated, tried
# strictly in order:the first is primary, each later model is a fallback used only
# when the previous fails with a retryable provider error (rate limit, quota,
# 5xx, model unavailable, transient network error). When AI_MODELS is unset
# the legacy single AI_MODEL is used as the only entry.
AI_MODELS = [
    model.strip() for model in os.getenv('AI_MODELS', '').split(',') if model.strip()
] or [AI_MODEL]
AI_MODELS = list(dict.fromkeys(AI_MODELS)) or [AI_MODEL]
AI_BASE_URL = os.getenv('AI_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/models')
# Per-attempt HTTP timeout (seconds). Key fallback is sequential, so worst case
# is ~len(GEMINI_API_KEYS) * len(AI_MODELS) * AI_REQUEST_TIMEOUT.
AI_REQUEST_TIMEOUT = float(os.getenv('AI_REQUEST_TIMEOUT', '30'))
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {name} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO')},
        'taskflow': {'handlers': ['console'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'), 'propagate': False},
    },
}

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'


CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://taskboard-x6ef.onrender.com",
    "https://taskboard-puce-two.vercel.app",
]

# NOTE: CORS_ALLOWED_ORIGIN_REGEXES is defined once above (near the other CORS
# settings). Do not redefine it further down — a duplicate silently overwrites
# the earlier value and any drift between them causes confusing CORS failures.