#!/usr/bin/env python3

"""Worker or downloader code for Pervellam"""

import argparse
import subprocess
import datetime
import time
import warnings
import pervellam_client
import config

class DLPJob:
    """A yt-dlp job"""
    def __init__(self, url):
        self.subp = subprocess.Popen([config.MYDLP, url])
    def status(self):
        """Return True if still running, False otherwise"""
        return bool(self.subp.poll() is None)
    def stop(self):
        """Ask dlp to stop"""
        self.subp.send_signal(2)
        self.subp.wait()
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
    myd = DLPJob(myj.get()["url"])
    print('Job commenced, doing initial update...')
    # TODO add fname
    myj.update({'started': datetime.datetime.now().isoformat(),
                'updated': datetime.datetime.now().isoformat(),
                'status': 'running'},
               retry=True)
    print('Looping and waiting...')
    while True:
        time.sleep(60)
        if myj.get()["status"] == "stopreq":
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
            myj.update({'updated': datetime.datetime.now().isoformat()})
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
