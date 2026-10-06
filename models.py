from datetime import date, datetime
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # hod|staff|mentor|student
    pw_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120)); is_demo = db.Column(db.Boolean, default=False)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reg_no = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    programme = db.Column(db.String(60), nullable=False)
    semester = db.Column(db.String(5), nullable=False)
    created = db.Column(db.Date, default=date.today)
    email = db.Column(db.String(120)); phone = db.Column(db.String(20))
    address = db.Column(db.String(200)); bio = db.Column(db.Text); photo = db.Column(db.String(80))
    is_demo = db.Column(db.Boolean, default=False)

class MentorGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    programme = db.Column(db.String(60)); academic_year = db.Column(db.String(10))
    semester = db.Column(db.String(5)); description = db.Column(db.String(200))
    mentor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(10), default='active')
    mentor = db.relationship('User')

class MentorAssignment(db.Model):
    """Historical allocation: a row is never overwritten, only closed (end_date set)."""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), index=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    group_id = db.Column(db.Integer, db.ForeignKey('mentor_group.id'))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    reason = db.Column(db.String(200)); by_user = db.Column(db.Integer, db.ForeignKey('user.id'))
    student = db.relationship('Student'); mentor = db.relationship('User', foreign_keys=[mentor_id])
    group = db.relationship('MentorGroup')

class AcademicRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), index=True)
    period = db.Column(db.Integer, nullable=False)  # 1..n
    period_date = db.Column(db.Date)
    attendance = db.Column(db.Float); assessment = db.Column(db.Float)
    assignment_pct = db.Column(db.Float); late_submissions = db.Column(db.Integer, default=0)

class SupportRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), index=True)
    category = db.Column(db.String(40)); message = db.Column(db.Text)
    status = db.Column(db.String(20), default='Submitted')
    response = db.Column(db.Text); created = db.Column(db.DateTime, default=datetime.utcnow)
    student = db.relationship('Student')

class Intervention(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), index=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # mentor at time of record
    itype = db.Column(db.String(40)); description = db.Column(db.Text)
    action_taken = db.Column(db.Text); student_response = db.Column(db.Text)
    on_date = db.Column(db.Date, default=date.today)
    follow_up_date = db.Column(db.Date); follow_up_done = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='In Progress')
    student = db.relationship('Student'); mentor = db.relationship('User')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    text = db.Column(db.String(200)); created = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer); action = db.Column(db.String(60))
    detail = db.Column(db.String(300)); created = db.Column(db.DateTime, default=datetime.utcnow)
