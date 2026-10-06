import secrets
from functools import wraps
from flask import session, abort, request, redirect, url_for, g
from models import db, User, Notification, AuditLog

def csrf_token():
    if '_csrf' not in session: session['_csrf'] = secrets.token_hex(16)
    return session['_csrf']

def init_security(app):
    app.jinja_env.globals['csrf_token'] = csrf_token
    @app.before_request
    def _guard():
        g.user = db.session.get(User, session['uid']) if 'uid' in session else None
        if request.method == 'POST' and request.form.get('_csrf') != session.get('_csrf'):
            abort(400, 'Invalid CSRF token')
    @app.context_processor
    def _ctx():
        n = Notification.query.filter_by(user_id=g.user.id, read=False).count() if g.user else 0
        return dict(me=g.user, unread=n)

def roles_required(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if not g.user: return redirect(url_for('auth.login'))
            if g.user.role not in roles: abort(403)  # enforced server-side, not just hidden menus
            return f(*a, **k)
        return w
    return deco

def audit(action, detail):
    db.session.add(AuditLog(user_id=g.user.id if g.get('user') else None, action=action, detail=detail[:300]))

def notify(user_id, text):
    if user_id: db.session.add(Notification(user_id=user_id, text=text))
