from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, abort, flash, g, Response
from werkzeug.security import check_password_hash
import csv, io
from models import *
from security import roles_required, audit, notify
import mentorship as ms
from analytics import student_signal, before_after

auth = Blueprint('auth', __name__); admin = Blueprint('admin', __name__)
mentor = Blueprint('mentor', __name__); student = Blueprint('student', __name__)
ITYPES = ['Mentor Meeting','Academic Guidance','Study Planning','Assignment Support','Attendance Discussion',
          'Course Guidance','Peer Support','Resource Referral','Other']
CATS = ['Academic Help','Attendance Issue','Assignment Difficulty','Course Difficulty',
        'Personal/General Academic Support','Mentor Discussion','Other']

@auth.route('/')
def home():
    if not g.user: return redirect(url_for('auth.login'))
    return redirect(url_for({'hod':'admin','staff':'admin','mentor':'mentor','student':'student'}[g.user.role]+'.dashboard'))

@auth.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(username=request.form.get('username','').strip()).first()
        if u and check_password_hash(u.pw_hash, request.form.get('password','')):
            session.clear(); session['uid'] = u.id
            g.user = u; audit('login', u.username); db.session.commit()
            return redirect(url_for('auth.home'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

@auth.route('/logout', methods=['POST'])
def logout():
    session.clear(); return redirect(url_for('auth.login'))

@auth.route('/notifications')
def notifications():
    if not g.user: return redirect(url_for('auth.login'))
    items = Notification.query.filter_by(user_id=g.user.id).order_by(Notification.created.desc()).limit(50).all()
    for n in items: n.read = True
    db.session.commit()
    return render_template('notifications.html', items=items)

# ---------------- HOD / OFFICE STAFF ----------------
def status_counts(studs):
    c = {'Stable':0,'Watch':0,'Support Suggested':0,'Priority Review':0}
    for s in studs: c[student_signal(s.id)['level']] += 1
    return c

@admin.route('/admin')
@roles_required('hod','staff')
def dashboard():
    studs = Student.query.all(); un = ms.unassigned()
    ctx = dict(total=len(studs), mentors=User.query.filter_by(role='mentor').count(),
               groups=MentorGroup.query.count(), un=un,
               open_req=SupportRequest.query.filter(SupportRequest.status!='Resolved').count(),
               fu_due=Intervention.query.filter(Intervention.follow_up_date <= date.today(), Intervention.follow_up_done==False).count())
    # Staff do not see sensitive analytics (spec: restricted for Office Staff)
    ctx['counts'] = status_counts(studs) if g.user.role == 'hod' else None
    return render_template('admin_dashboard.html', **ctx)

@admin.route('/admin/assign', methods=['GET','POST'])
@roles_required('hod','staff')
def assign_page():
    mentors = User.query.filter_by(role='mentor').all()
    groups = MentorGroup.query.all()
    if request.method == 'POST':
        ids = [int(x) for x in request.form.getlist('students')]
        m = db.session.get(User, int(request.form['mentor'])); grp = db.session.get(MentorGroup, int(request.form['group']))
        if not ids or not m or not grp or m.role != 'mentor': flash('Select students, a mentor and a group.', 'error')
        elif request.form.get('confirmed') != '1':
            sel = Student.query.filter(Student.id.in_(ids)).all()
            return render_template('confirm_assign.html', sel=sel, m=m, grp=grp)
        else:
            reason = request.form.get('reason') or 'Allocation'
            n = ms.assign(ids, m.id, grp.id, g.user.id, reason)
            for sid in ids: pass
            notify(m.id, f'{n} student(s) assigned to you in {grp.name}.')
            audit('assign', f'{g.user.name} assigned {n} student(s) to {m.name} ({grp.name}): {reason}')
            db.session.commit(); flash(f'{n} students assigned to {m.name} under {grp.name}.', 'ok')
            return redirect(url_for('admin.assign_page'))
    studs = Student.query.order_by(Student.reg_no).all()
    cur = {s.id: ms.active_assignment(s.id) for s in studs}
    return render_template('assign.html', studs=studs, cur=cur, mentors=mentors, groups=groups)

@admin.route('/admin/groups', methods=['GET','POST'])
@roles_required('hod','staff')
def groups():
    if request.method == 'POST':
        gr = MentorGroup(name=request.form['name'], programme=request.form['programme'], academic_year=request.form['year'],
                         semester=request.form['semester'], mentor_id=int(request.form['mentor']),
                         description=request.form.get('description',''))
        db.session.add(gr); audit('group_create', f'{g.user.name} created {gr.name}'); db.session.commit()
        flash('Mentor group created.', 'ok'); return redirect(url_for('admin.groups'))
    return render_template('groups.html', groups=MentorGroup.query.all(), mentors=User.query.filter_by(role='mentor').all(),
                           size={gr.id: MentorAssignment.query.filter_by(group_id=gr.id, end_date=None).count() for gr in MentorGroup.query.all()})

@admin.route('/admin/workload')
@roles_required('hod','staff')
def workload():
    rows = []
    for m in User.query.filter_by(role='mentor').all():
        ss = ms.students_of(m.id)
        c = status_counts(ss) if g.user.role == 'hod' else {}
        due = Intervention.query.filter(Intervention.mentor_id==m.id, Intervention.follow_up_date<=date.today(), Intervention.follow_up_done==False).count()
        rows.append(dict(m=m, groups=MentorGroup.query.filter_by(mentor_id=m.id).count(), n=len(ss), c=c, due=due))
    key = request.args.get('sort', 'n'); rows.sort(key=lambda r: r.get(key, 0) if key in ('n','groups','due') else 0, reverse=True)
    return render_template('workload.html', rows=rows)

@admin.route('/admin/history/<reg>')
@roles_required('hod','staff')
def history(reg):
    s = Student.query.filter_by(reg_no=reg).first_or_404()
    h = MentorAssignment.query.filter_by(student_id=s.id).order_by(MentorAssignment.start_date).all()
    return render_template('history.html', s=s, h=h, groups=MentorGroup.query.all())

@admin.route('/admin/reassign', methods=['POST'])
@roles_required('hod','staff')
def reassign():
    s = Student.query.filter_by(reg_no=request.form['reg']).first_or_404()
    grp = db.session.get(MentorGroup, int(request.form['group']))
    eff = datetime.strptime(request.form['effective'], '%Y-%m-%d').date()
    old = ms.active_assignment(s.id)
    ms.assign([s.id], grp.mentor_id, grp.id, g.user.id, request.form.get('reason','Reassignment'), eff)
    notify(grp.mentor_id, f'{s.reg_no} transferred to you.'); notify(s.user_id, 'Your mentor has been updated.')
    audit('reassign', f'{s.reg_no}: {old.mentor.name if old else "none"} -> {grp.mentor.name} eff {eff} ({request.form.get("reason","")})')
    db.session.commit(); return redirect(url_for('admin.history', reg=s.reg_no))

@admin.route('/admin/outcomes')
@roles_required('hod')
def outcomes():
    return render_template('outcomes.html', r=before_after(Intervention.query.all()),
                           req=SupportRequest.query.count(), ivs=Intervention.query.count())

@admin.route('/admin/audit')
@roles_required('hod')
def audit_log():
    return render_template('audit.html', logs=AuditLog.query.order_by(AuditLog.created.desc()).limit(100).all())

@admin.route('/admin/export/students.csv')
@roles_required('hod')
def export_csv():
    out = io.StringIO(); w = csv.writer(out); w.writerow(['Reg No','Name','Programme','Semester','Status','AMI','Mentor'])
    for s in Student.query.order_by(Student.reg_no):
        sg = student_signal(s.id); a = ms.active_assignment(s.id)
        w.writerow([s.reg_no, s.name, s.programme, s.semester, sg['level'], sg['ami'], a.mentor.name if a else 'Unassigned'])
    audit('export', 'students.csv'); db.session.commit()
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=students.csv'})

# ---------------- MENTOR ----------------
@mentor.route('/mentor')
@roles_required('mentor')
def dashboard():
    studs = ms.students_of(g.user.id); rows = [(s, student_signal(s.id)) for s in studs]
    q = request.args.get('q','').lower(); f = request.args.get('level','')
    rows = [r for r in rows if (q in r[0].name.lower() or q in r[0].reg_no.lower()) and (not f or r[1]['level']==f)]
    counts = status_counts(studs)
    today = date.today()
    fus = Intervention.query.filter_by(mentor_id=g.user.id, follow_up_done=False).filter(Intervention.follow_up_date.isnot(None)).order_by(Intervention.follow_up_date).all()
    fus = [x for x in fus if ms.mentor_owns(g.user.id, x.student_id)]
    reqs = [r for r in SupportRequest.query.filter(SupportRequest.status!='Resolved').all() if ms.mentor_owns(g.user.id, r.student_id)]
    return render_template('mentor_dashboard.html', rows=rows, counts=counts, n=len(studs), fus=fus, reqs=reqs, today=today)

@mentor.route('/mentor/student/<reg>', methods=['GET','POST'])
@roles_required('mentor')
def student_view(reg):
    s = Student.query.filter_by(reg_no=reg).first_or_404()
    if not ms.mentor_owns(g.user.id, s.id): abort(403)  # IDOR guard
    if request.method == 'POST':
        fu = request.form.get('follow_up')
        iv = Intervention(student_id=s.id, mentor_id=g.user.id, itype=request.form['itype'] if request.form['itype'] in ITYPES else 'Other',
                          description=request.form['description'], action_taken=request.form.get('action',''),
                          follow_up_date=datetime.strptime(fu,'%Y-%m-%d').date() if fu else None, status=request.form.get('status','In Progress'))
        db.session.add(iv); notify(s.user_id, 'Your mentor has recorded a follow-up plan.' if fu else 'Your mentor recorded a support note.')
        audit('intervention', f'{g.user.name} recorded {iv.itype} for {s.reg_no}'); db.session.commit()
        flash('Intervention recorded.', 'ok'); return redirect(url_for('mentor.student_view', reg=reg))
    ivs = Intervention.query.filter_by(student_id=s.id).order_by(Intervention.on_date.desc()).all()
    reqs = SupportRequest.query.filter_by(student_id=s.id).order_by(SupportRequest.created.desc()).all()
    return render_template('student_profile.html', s=s, sg=student_signal(s.id), ivs=ivs, reqs=reqs, itypes=ITYPES,
                           a=ms.active_assignment(s.id))

@mentor.route('/mentor/followup/<int:iid>', methods=['POST'])
@roles_required('mentor')
def complete_followup(iid):
    iv = db.session.get(Intervention, iid) or abort(404)
    if not ms.mentor_owns(g.user.id, iv.student_id): abort(403)
    iv.follow_up_done = True; audit('followup_done', f'{iv.student.reg_no}'); db.session.commit()
    return redirect(url_for('mentor.dashboard'))

@mentor.route('/mentor/request/<int:rid>', methods=['POST'])
@roles_required('mentor')
def respond(rid):
    r = db.session.get(SupportRequest, rid) or abort(404)
    if not ms.mentor_owns(g.user.id, r.student_id): abort(403)
    r.response = request.form['response']; r.status = request.form.get('status','In Progress')
    notify(r.student.user_id, 'Your mentor responded to your support request.')
    audit('request_response', r.student.reg_no); db.session.commit(); return redirect(url_for('mentor.dashboard'))

# ---------------- STUDENT ----------------
def me_student():
    s = Student.query.filter_by(user_id=g.user.id).first() or abort(404); return s

@student.route('/student')
@roles_required('student')
def dashboard():
    s = me_student(); a = ms.active_assignment(s.id)
    return render_template('student_dashboard.html', s=s, sg=student_signal(s.id), a=a,
                           reqs=SupportRequest.query.filter_by(student_id=s.id).order_by(SupportRequest.created.desc()).all())

@student.route('/student/request', methods=['GET','POST'])
@roles_required('student')
def request_support():
    s = me_student()
    if request.method == 'POST':
        msg = request.form.get('message','').strip()
        if not msg: flash('Please describe what support you need.', 'error')
        else:
            db.session.add(SupportRequest(student_id=s.id, category=request.form['category'] if request.form['category'] in CATS else 'Other', message=msg))
            a = ms.active_assignment(s.id)
            if a: notify(a.mentor_id, f'New support request from {s.reg_no}.')
            notify(s.user_id, 'Your support request was received.')
            audit('support_request', s.reg_no); db.session.commit(); flash('Request submitted.', 'ok')
            return redirect(url_for('student.dashboard'))
    return render_template('request.html', cats=CATS)

@auth.route('/responsible-use')
def responsible():
    return render_template('responsible.html')

# ---------------- STUDENT PROFILE, PHOTO, ACCOUNT ----------------
import os, uuid
from flask import current_app, send_from_directory
from werkzeug.security import generate_password_hash

def _photo_dir():
    d = os.path.join(current_app.instance_path, 'photos'); os.makedirs(d, exist_ok=True); return d

def _image_ext(head):
    if head.startswith(b'\xff\xd8\xff'): return 'jpg'
    if head.startswith(b'\x89PNG\r\n\x1a\n'): return 'png'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP': return 'webp'
    return None

@student.route('/student/profile', methods=['GET', 'POST'])
@roles_required('student')
def profile():
    s = me_student()
    if request.method == 'POST':
        s.bio = request.form.get('bio', '').strip()[:1000]; s.phone = request.form.get('phone', '').strip()[:20]
        s.email = request.form.get('email', '').strip()[:120]; s.address = request.form.get('address', '').strip()[:200]
        f = request.files.get('photo')
        if f and f.filename:
            data = f.read(); ext = _image_ext(data[:16])
            if not ext or len(data) > 2 * 1024 * 1024: flash('Photo must be a JPG, PNG or WEBP image under 2 MB.', 'error'); return redirect(url_for('student.profile'))
            name = f'{uuid.uuid4().hex}.{ext}'; open(os.path.join(_photo_dir(), name), 'wb').write(data)
            if s.photo and os.path.exists(os.path.join(_photo_dir(), s.photo)): os.remove(os.path.join(_photo_dir(), s.photo))
            s.photo = name
        audit('profile_update', s.reg_no); db.session.commit(); flash('Profile saved.', 'ok'); return redirect(url_for('student.profile'))
    return render_template('profile.html', s=s)

@student.route('/student/requests')
@roles_required('student')
def my_requests():
    s = me_student()
    return render_template('my_requests.html', reqs=SupportRequest.query.filter_by(student_id=s.id).order_by(SupportRequest.created.desc()).all())

@auth.route('/photo/<reg>')
def photo(reg):
    """Authorised photo access: the student, their current mentor, or admin roles only."""
    if not g.user: abort(403)
    s = Student.query.filter_by(reg_no=reg).first_or_404()
    ok = (g.user.role in ('hod', 'staff') or (g.user.role == 'student' and s.user_id == g.user.id)
          or (g.user.role == 'mentor' and ms.mentor_owns(g.user.id, s.id)))
    if not ok or not s.photo: abort(404 if ok else 403)
    return send_from_directory(_photo_dir(), s.photo)

@auth.route('/account', methods=['GET', 'POST'])
def account():
    if not g.user: return redirect(url_for('auth.login'))
    if request.method == 'POST':
        new = request.form.get('new', '')
        if not check_password_hash(g.user.pw_hash, request.form.get('old', '')): flash('Current password is incorrect.', 'error')
        elif len(new) < 8 or new != request.form.get('again'): flash('New password must be at least 8 characters and match the confirmation.', 'error')
        else:
            g.user.pw_hash = generate_password_hash(new); audit('password_change', g.user.username); db.session.commit(); flash('Password changed.', 'ok')
    return render_template('account.html')
