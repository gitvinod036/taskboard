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
CORS_ALLOW_CREDENTIALS = True
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:8000/api/auth/google/callback/')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5174')
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
    "https://taskboard-x6ef.onrender.com",
    "https://taskboard-puce-two.vercel.app",
]