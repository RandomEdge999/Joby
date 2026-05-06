from datetime import datetime

from app.db import SessionLocal
from app.models import Company, Job, JobEvent
from app.services.diffing import snapshot_active, emit_events


def _job(db, tag, title="Engineer", location="NYC", salary_min=None):
    c = Company(name=f"C-{tag}", normalized_name=f"diff-co-{tag}")
    db.add(c); db.commit(); db.refresh(c)
    now = datetime.utcnow()
    j = Job(source="greenhouse", external_job_id=f"diff-{tag}",
            title=title, company_id=c.id, location_raw=location,
            salary_min=salary_min,
            first_seen_at=now, last_seen_at=now, is_active=True)
    db.add(j); db.commit(); db.refresh(j)
    return j


def test_emit_events_new_change_disappear():
    db = SessionLocal()
    try:
        # Prev state: job A existed, job B will disappear
        a = _job(db, "a", title="SWE", location="NYC")
        b = _job(db, "b", title="PM", location="SF")
        before = snapshot_active(db)

        # Simulate run: A comes back with a title change; B disappears; C is new
        a.title = "Senior SWE"
        db.commit()
        c = _job(db, "c", title="Data", location="Remote")
        after = [a, c]
        newly = {c.id}

        events = emit_events(db, watch_id=None, before=before,
                             after_jobs=after, first_seen_this_run=newly)
        types = [e.event_type for e in events]
        assert "new" in types
        assert "material_change" in types
        assert "disappeared" in types

        # disappeared event is for b
        dj = [e for e in events if e.event_type == "disappeared"]
        assert any(e.job_id == b.id for e in dj)
    finally:
        db.close()
