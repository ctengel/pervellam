#!/usr/bin/env python3

"""Worker or downloader code for Pervellam"""

import argparse
import subprocess
import datetime
import time
import warnings
import pervellam_client
import config

WAIT_FOR_KILL = 200

class DLPJob:
    """A yt-dlp job"""
    def __init__(self, url):
        self.subp = subprocess.Popen([config.MYDLP,
                                      '--restrict-filenames',
                                      '--write-info-json',
                                      url])
    def status(self):
        """Return True if still running, False otherwise"""
        return bool(self.subp.poll() is None)
    def stop(self):
        """Ask dlp to stop"""
        self.subp.send_signal(2)
        try:
            self.subp.wait(WAIT_FOR_KILL)
        except subprocess.TimeoutExpired:
            warnings.warn('Kill request timeout; retrying...')
            self.subp.send_signal(2)
            self.subp.wait()
        finally:
            self.close()
    def close(self):
        """Clean up resources"""
        # TODO do we need this?
        #self.subp.close()

def run_one(server, dler):
    """Check for a new job, assign, run, wait to finish or stop"""
    print(f'Worker {dler} looking for jobs...')
    myp = pervellam_client.Pervellam(server, dler)
    myj = myp.assign_job()
    if not myj:
        print('No jobs found')
        return
    print(f'Assigned job {myj.job_id}; getting more details...')
    job_info = myj.get(retry=True)
    assert job_info["dler"] == dler
    myd = DLPJob(job_info["url"])
    print('Job commenced, doing initial update...')
    # TODO add fname
    job_info = myj.update({'started': datetime.datetime.now().isoformat(),
                           'updated': datetime.datetime.now().isoformat(),
                           'status': 'running'},
                          retry=True)
    print('Looping and waiting...')
    while True:
        if job_info["dler"] != dler:
            warnings.warn('Conflict dectected, self destructing...')
            myd.stop()
            # TODO throw a better exception here
            assert False
        time.sleep(60)
        try:
            pjs = myj.get()["status"]
        except pervellam_client.requests.exceptions.RequestException:
            # NOTE this does not use the myj.update(retry=True) logic as above
            #      because since this download is still healthy better to stay in normal loop
            warnings.warn('Cannot get status from Pervellam server, will retry in a minute...')
            continue
        if pjs == "stopreq":
            print('Recieved stop request...')
            myd.stop()
            print('Job stopped!')
            myj.update({'status': 'stopped'}, retry=True)
            return
        if not myd.status():
            print('Job stopped organically!')
            myd.close()
            myj.update({'status': 'ended'}, retry=True)
            return
        try:
            # TODO add size and/or actual file mtime
            job_info = myj.update({'updated': datetime.datetime.now().isoformat()})
        except pervellam_client.requests.exceptions.RequestException:
            # NOTE this does not use the myj.update(retry=True) logic as above
            #      because since this download is still healthy better to stay in normal loop
            warnings.warn('Cannot update Pervellam server, will retry in a minute...')
            continue


def run_cli():
    """Basic CLI"""
    parser = argparse.ArgumentParser(description='Pervellam worker')
    parser.add_argument('server', help='Pervellam server URL')
    parser.add_argument('dler', help='Name of this worker')
    args = parser.parse_args()
    run_one(args.server, args.dler)

if __name__ == '__main__':
    run_cli()
