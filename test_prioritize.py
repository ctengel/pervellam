"""Tests for prioritize.py's handling of jobs stuck in 'upload' status (#45)."""

import prioritize


class FakeTw:
    """Minimal stand-in for tw.Tw: everyone in `live` is followed and live."""
    def __init__(self, live):
        self.live = live

    def followed(self):
        return [{'user_login': login} for login in self.live]


class FakeJob:
    """Minimal stand-in for pervellam_client.Job: records stop() calls."""
    def __init__(self, pvo, job_id):
        self.pvo = pvo
        self.job_id = job_id

    def stop(self):
        self.pvo.stopped.append(self.job_id)


class FakePervellam:
    """Minimal stand-in for pervellam_client.Pervellam driven by a plain job list.

    Each job is a dict with id/url/status; new_job()/get_job().stop() just
    record what prioritize.py tried to do, so tests can assert on them.
    """
    def __init__(self, jobs):
        self.jobs = jobs
        self.added = []
        self.stopped = []

    def list_jobs(self, filt='active'):  # noqa: ARG002 - filt unused, tests build 'active' lists directly
        return self.jobs

    def new_job(self, url):
        self.added.append(url)

    def get_job(self, job_id):
        return FakeJob(self, job_id)


def job(job_id, name, status):
    return {"id": job_id, "url": f"https://www.website.com/{name}", "status": status}


def test_prioritize_reschedules_stuck_upload_job():
    """A priority whose only job is stuck in 'upload' gets a fresh job (#45)."""
    jobs = [job(1, "alice", "upload")]
    pvo = FakePervellam(jobs)
    two = FakeTw(live=["alice", "bob"])
    prioritize.prioritize(pvo, two, ["alice", "bob"], count=5)
    assert "https://www.website.com/alice" in pvo.added


def test_prioritize_does_not_reschedule_actively_running_job():
    """A priority with a genuinely active job is left alone."""
    jobs = [job(1, "alice", "running")]
    pvo = FakePervellam(jobs)
    two = FakeTw(live=["alice"])
    prioritize.prioritize(pvo, two, ["alice"], count=5)
    assert pvo.added == []


def test_prioritize_never_stops_an_upload_job():
    """A stuck 'upload' job is never passed to .stop(), even if it would
    otherwise be pruned as excess (it's simply invisible to the remove loop)."""
    jobs = [job(1, "alice", "upload")]
    pvo = FakePervellam(jobs)
    two = FakeTw(live=["alice"])
    # count=0 forces the remove loop to consider pruning everything in `running`
    prioritize.prioritize(pvo, two, ["alice"], count=0)
    assert pvo.stopped == []


def test_pri_naieve_reschedules_stuck_upload_job():
    jobs = [job(1, "alice", "upload")]
    pvo = FakePervellam(jobs)
    prioritize.pri_naieve(pvo, ["alice"])
    assert pvo.added == ["https://www.website.com/alice"]


def test_pri_naieve_does_not_reschedule_actively_running_job():
    jobs = [job(1, "alice", "new")]
    pvo = FakePervellam(jobs)
    prioritize.pri_naieve(pvo, ["alice"])
    assert pvo.added == []
