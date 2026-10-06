"""Prototype statistical early-support rules. NOT a validated predictive model."""
from scipy import stats
from models import AcademicRecord, Intervention

# PROTOTYPE weights - replace with your existing AMI formula from the original project.
AMI_WEIGHTS = dict(attendance=0.35, assessment=0.40, assignment=0.25)

def ami(r):
    return round(AMI_WEIGHTS['attendance']*r.attendance + AMI_WEIGHTS['assessment']*r.assessment
                 + AMI_WEIGHTS['assignment']*r.assignment_pct, 1)

LEVELS = {0: 'Stable', 1: 'Watch', 2: 'Support Suggested', 3: 'Priority Review'}

def student_signal(student_id):
    recs = AcademicRecord.query.filter_by(student_id=student_id).order_by(AcademicRecord.period).all()
    if not recs: return dict(level='Stable', ami=None, trend='→ No data', reasons=[], recs=[])
    cur, prev = recs[-1], (recs[-2] if len(recs) > 1 else None)
    reasons, pts = [], 0
    if prev:
        d_att, d_ass = cur.attendance - prev.attendance, cur.assessment - prev.assessment
        if d_att <= -5: pts += 1; reasons.append(f'Attendance decreased by {abs(d_att):.1f} percentage points since the previous period.')
        if d_ass <= -5: pts += 1; reasons.append(f'Assessment performance decreased by {abs(d_ass):.1f} percentage points.')
    if cur.late_submissions >= 2: pts += 1; reasons.append(f'{cur.late_submissions} late assignment submissions this period.')
    if ami(cur) < 55: pts += 1; reasons.append('Academic Momentum is currently below 55 (prototype threshold).')
    delta = ami(cur) - ami(prev) if prev else 0
    trend = '↑ Improving' if delta >= 2 else '↓ Declining' if delta <= -2 else '→ Stable'
    return dict(level=LEVELS[min(pts, 3)], ami=ami(cur), trend=trend, reasons=reasons, recs=recs, cur=cur, prev=prev)

def before_after(interventions):
    """Paired before/after on AMI: last record on/before intervention vs latest record."""
    pairs = []
    for iv in interventions:
        recs = AcademicRecord.query.filter_by(student_id=iv.student_id).order_by(AcademicRecord.period).all()
        before = [r for r in recs if r.period_date and r.period_date <= iv.on_date]
        after = [r for r in recs if r.period_date and r.period_date > iv.on_date]
        if before and after: pairs.append((ami(before[-1]), ami(after[-1])))
    n = len(pairs)
    if n < 3: return dict(n=n, note='At least 3 paired observations are needed for a before/after test.')
    b, a = [p[0] for p in pairs], [p[1] for p in pairs]
    diffs = [y - x for x, y in zip(b, a)]
    t = stats.ttest_rel(a, b)
    try: w = stats.wilcoxon(diffs).pvalue
    except ValueError: w = None
    mean_d = sum(diffs) / n
    sd = (sum((d - mean_d)**2 for d in diffs) / (n - 1)) ** .5
    ci = stats.t.interval(0.95, n-1, loc=mean_d, scale=sd/n**.5) if sd else (mean_d, mean_d)
    return dict(n=n, before=round(sum(b)/n,1), after=round(sum(a)/n,1), diff=round(mean_d,2),
                dz=round(mean_d/sd, 2) if sd else None, p_t=round(float(t.pvalue),4),
                p_w=None if w is None else round(float(w),4), ci=(round(ci[0],2), round(ci[1],2)),
                note='Indicators changed after the intervention. This design cannot establish that the intervention caused the change.')
