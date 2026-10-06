import os
from flask import Flask, render_template
from models import db
from security import init_security
from routes import auth, admin, mentor, student
from manage import manage

def ensure_columns():
    """Add columns introduced after a database was first created (SQLite, non-destructive)."""
    from sqlalchemy import text
    want = {'student': {'email':'VARCHAR(120)','phone':'VARCHAR(20)','address':'VARCHAR(200)','bio':'TEXT','photo':'VARCHAR(80)','is_demo':'BOOLEAN DEFAULT 0'},
            'user': {'email':'VARCHAR(120)','is_demo':'BOOLEAN DEFAULT 0'}}
    for t, cols in want.items():
        have = {r[1] for r in db.session.execute(text(f'PRAGMA table_info("{t}")'))}
        for c, typ in cols.items():
            if c not in have: db.session.execute(text(f'ALTER TABLE "{t}" ADD COLUMN {c} {typ}'))
    db.session.commit()

def create_app(db_uri=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-only-change-me'),
                      SQLALCHEMY_DATABASE_URI=db_uri or 'sqlite:///campus_saathi.db',
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('HTTPS') == '1', MAX_CONTENT_LENGTH=6*1024*1024)
    db.init_app(app); init_security(app)
    for bp in (auth, admin, mentor, student, manage): app.register_blueprint(bp)
    @app.errorhandler(403)
    def _403(e): return render_template('error.html', code=403, msg='You do not have access to this page.'), 403
    @app.errorhandler(404)
    def _404(e): return render_template('error.html', code=404, msg='Page not found.'), 404
    with app.app_context():
        db.create_all(); ensure_columns()
        from models import User
        if not User.query.first():
            if os.environ.get('NO_DEMO') == '1':
                from werkzeug.security import generate_password_hash as H
                db.session.add(User(username='hod', name='HOD', role='hod', pw_hash=H(os.environ.get('HOD_PASSWORD','ChangeMe@123')))); db.session.commit()
            else:
                from seed import seed; seed()
    return app

if __name__ == '__main__':
    create_app().run(debug=False)
