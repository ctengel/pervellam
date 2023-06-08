"""Object oriented Pervellam client library"""

import time
import requests

RETRIES = 3
RETRY_WAIT = 30

class Pervellam:
    """Deal with a Pervallam server"""
    def __init__(self, url, me=None):
        self.url = url
        self.myname = me
    def req(self, url, method='GET', params=None, json=None, decode=True):
        """Run a Python Requests request"""
        req = requests.request(method, self.url + url, params=params, json=json)
        req.raise_for_status()
        if decode:
            return req.json()
        return None
    def assign_job(self):
        """Find and assign a job"""
        jobs = self.list_jobs('unassigned')
        if not jobs:
            return None
        myjob = Job(self, jobs[0]["id"])
        myjob.assign(self.myname)
        return myjob
    def new_job(self, url):
        """Submit a new job"""
        return Job(self, self.req('jobs/', 'POST', json={"url": url})["id"])
    def get_job(self, job_id):
        """Return existing job object"""
        return Job(self, job_id)
    def list_jobs(self, filt='active'):
        """List some or all jobs"""
        # TODO use objects?
        params = None
        if filt:
            params={'filt': filt}
        return self.req('jobs/', params=params)



class Job:
    """Deal with a Pervellam job"""
    def __init__(self, pervellam, job_id):
        self.pervellam = pervellam
        self.job_id = job_id
    def assign(self, assign_to):
        """Assign this job to a worker"""
        self.pervellam.req(f"jobs/{self.job_id}/assign",
                           'POST',
                           json={"dler": assign_to},
                           decode=False)
    def get(self):
        """Get current info on this job"""
        return self.pervellam.req(f"jobs/{self.job_id}")
    def update(self, info, retry=False):
        """Update this job, optionally retrying on error"""
        retries = 1
        # TODO consider using requests.adapters.Retry
        if retry:
            retries = RETRIES
        while True:
            try:
                return self.pervellam.req(f"jobs/{self.job_id}", 'PATCH', json=info)
            except requests.exceptions.RequestException as exception:
                retries -= 1
                if retries:
                    time.sleep(RETRY_WAIT)
                else:
                    raise exception
        assert False
    def stop(self):
        """Stop this job"""
        # TODO add force option
        self.pervellam.req(f"jobs/{self.job_id}/stop", 'POST', decode=False)
