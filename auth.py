"""
Authentication utilities and decorators
"""
import os
import json
import pyotp
import qrcode
import base64
import io
import logging
import traceback
from functools import wraps
from flask import session, redirect, url_for, request, abort
from authlib.integrations.flask_client import OAuth
from config import TOTP_SECRETS_PATH, TOTP_ISSUER, AUTH_LOG_PATH, ALLOWED_USERS, ENABLE_OAUTH_LOGIN

# Setup auth logger
os.makedirs(os.path.dirname(AUTH_LOG_PATH), exist_ok=True)
auth_logger = logging.getLogger('auth_debug')
if not auth_logger.handlers:
    auth_logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(AUTH_LOG_PATH, encoding='utf-8')
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    auth_logger.addHandler(file_handler)
    auth_logger.propagate = False

def load_totp_secrets():
    """Cargar secretos TOTP desde archivo"""
    if not os.path.exists(TOTP_SECRETS_PATH):
        return {}
    try:
        with open(TOTP_SECRETS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        print(f"Warning: Unable to load TOTP secrets: {exc}")
    return {}

def save_totp_secrets(secrets):
    """Guardar secretos TOTP en archivo"""
    try:
        with open(TOTP_SECRETS_PATH, 'w', encoding='utf-8') as f:
            json.dump(secrets, f, indent=2)
    except Exception as exc:
        print(f"Warning: Unable to persist TOTP secrets: {exc}")

TOTP_SECRETS = load_totp_secrets()

def is_user_allowed(email):
    """Verificar si un usuario está permitido"""
    if not email:
        return False
    if not ALLOWED_USERS:
        return True
    return email.lower() in ALLOWED_USERS

def get_user_totp_secret(email):
    """Obtener el secreto TOTP de un usuario"""
    return TOTP_SECRETS.get(email.lower())

def ensure_user_totp_secret(email):
    """Asegurar que un usuario tenga un secreto TOTP"""
    normalized = email.lower()
    secret = TOTP_SECRETS.get(normalized)
    if not secret:
        secret = pyotp.random_base32()
        TOTP_SECRETS[normalized] = secret
        save_totp_secrets(TOTP_SECRETS)
    return secret

def is_authenticated(app):
    """Verificar si el usuario está autenticado"""
    if not app.config.get('ENABLE_OAUTH_LOGIN'):
        return True
    return (
        session.get('user_email')
        and session.get('google_sub')
        and session.get('2fa_verified')
    )

def api_login_required(app):
    """Decorador para requerir autenticación en endpoints API"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not app.config.get('ENABLE_OAUTH_LOGIN'):
                return func(*args, **kwargs)
            if not is_authenticated(app):
                from flask import jsonify
                return jsonify({"success": False, "error": "Unauthorized"}), 401
            return func(*args, **kwargs)
        return wrapper
    return decorator

def login_required(app):
    """Decorador para requerir autenticación en vistas"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not app.config.get('ENABLE_OAUTH_LOGIN'):
                return view_func(*args, **kwargs)
            if is_authenticated(app):
                return view_func(*args, **kwargs)

            if session.get('pending_2fa'):
                return redirect(url_for('two_factor'))

            next_url = request.args.get('next') or request.path or '/'
            session['next_url'] = next_url
            return redirect(url_for('login_page', next=next_url))
        return wrapper
    return decorator

def get_next_url(default='/'):
    """Obtener la URL siguiente después del login"""
    return session.pop('next_url', None) or request.args.get('next') or default

def require_oauth(app):
    """Verificar que OAuth esté habilitado y configurado"""
    if not app.config.get('ENABLE_OAUTH_LOGIN'):
        abort(404, description="OAuth login is disabled.")
    if not (app.config.get('GOOGLE_CLIENT_ID') and app.config.get('GOOGLE_CLIENT_SECRET')):
        abort(503, description="Google OAuth is not configured.")
    return OAuth(app).create_client('google')

def generate_qr_code(provisioning_uri):
    """Generar código QR para TOTP"""
    buffer = io.BytesIO()
    qrcode.make(provisioning_uri).save(buffer, format='PNG')
    qr_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return qr_b64

