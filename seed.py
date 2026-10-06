"""DEMO MODE: synthetic data only. Not real student information."""
import random
from datetime import date, timedelta
from werkzeug.security import generate_password_hash as H
from models import *
import mentorship as ms

def seed():
    rnd = random.Random(7); pw = H('demo123')
    def U(un, name, role): u = User(username=un, name=name, role=role, pw_hash=pw, is_demo=True); db.session.add(u); return u
    U('hod','Dr. Raman','hod'); U('staff','Office Staff','staff')
    mentors = [U('priya','Dr. Priya','mentor'), U('kumar','Dr. Kumar','mentor'), U('anitha','Dr. Anitha','mentor')]
    db.session.flush()
    groups = []
    for m, nm in zip(mentors, ['M.Sc Statistics — Group A','M.Sc Statistics — Group B','M.Sc Applied Mathematics — Group A']):
        g = MentorGroup(name=nm, programme=nm.split(' — ')[0], academic_year='2026-27', semester='III', mentor_id=m.id); db.session.add(g); groups.append(g)
    db.session.flush()
    sizes = [15, 12, 8, 5]  # last 5 deliberately unassigned
    profiles = ['stable']*14 + ['decline']*10 + ['sharp']*5 + ['improve']*11
    rnd.shuffle(profiles); i = 0; today = date.today()
    for gi, sz in enumerate(sizes):
        for _ in range(sz):
            i += 1; reg = f'S25{i:02d}'
            u = U(f's{i:02d}', f'Student {i}', 'student'); db.session.flush()
            s = Student(user_id=u.id, reg_no=reg, name=f'Student {i}', programme='M.Sc Applied Mathematics' if gi==2 else 'M.Sc Statistics', semester='III', is_demo=True)
            db.session.add(s); db.session.flush()
            att, ass, asg = rnd.uniform(75,92), rnd.uniform(62,85), rnd.uniform(80,98); p = profiles[i-1]
            for per in range(1, 6):
                k = {'stable':0, 'decline':-3.2, 'sharp':-5.5, 'improve':2.5}[p]
                if p == 'improve' and per <= 2: k = -3
                att, ass = min(98, max(35, att + k + rnd.uniform(-1,1))), min(98, max(30, ass + k*0.9 + rnd.uniform(-1,1)))
                late = 0 if k >= 0 else rnd.choice([1,2,3])
                db.session.add(AcademicRecord(student_id=s.id, period=per, period_date=today - timedelta(days=(5-per)*21),
                                attendance=round(att,1), assessment=round(ass,1), assignment_pct=round(max(40,asg+k*1.5),1), late_submissions=late))
            if gi < 3:
                db.session.add(MentorAssignment(student_id=s.id, mentor_id=mentors[gi].id, group_id=groups[gi].id, start_date=today-timedelta(days=110), reason='Initial allocation'))
                if p in ('improve','decline') and rnd.random() < .7:
                    db.session.add(Intervention(student_id=s.id, mentor_id=mentors[gi].id, itype='Study Planning', description='Discussed study plan.',
                                    action_taken='Weekly plan agreed.', on_date=today-timedelta(days=50), follow_up_date=today+timedelta(days=rnd.choice([-2,0,3])), status='Follow-up Required'))
                if p == 'sharp':
                    db.session.add(SupportRequest(student_id=s.id, category='Course Difficulty', message='Finding Statistical Inference difficult.'))
    db.session.commit()
