#!/usr/bin/env python3

"""Worker or downloader code for Pervellam"""

import argparse
import subprocess
import datetime
import time
import warnings
import os
import pathlib
import tempfile
import obj_idx.dlp_lpm_meta as dlpmeta
import obj_idx.client as oiclient
import pervellam_client
import config

WAIT_FOR_KILL = 200
LPM_LIB = 'TWCH'


class DLPJob:
    """A yt-dlp job"""

    def __init__(self, url):
        self.subp = subprocess.Popen([config.MYDLP,
                                      '--restrict-filenames',
                                      '--write-info-json',
                                      url])

    def status(self):
        """Return True if still running, False otherwise"""
        # TODO concept of exit code
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

    def file_info(self):
        """Get info on download file

        (assumes download file is the largest file)
        """
        ourdir = pathlib.Path()
        files = [(f.stat().st_size, f.name, f.stat().st_mtime) for f in ourdir.iterdir()]
        files.sort(reverse=True)
        if not files:
            return {'fname': None,
                    'size': 0,
                    'mtime': None}
        ourfile = files[0]
        return {'fname': ourfile[1],
                'size': ourfile[0],
                'updated': datetime.datetime.fromtimestamp(ourfile[2],
                                                           datetime.timezone.utc).isoformat()}


def run_one(dler, myj):
    """Check for a new job, assign, run, wait to finish or stop"""
    print(f'Assigned job {myj.job_id}; getting more details...')
    job_info = myj.get(retry=True)
    assert job_info["dler"] == dler
    myd = DLPJob(job_info["url"])
    print('Job commenced, doing initial update...')
    job_info = myj.update({'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           'updated': datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
            # NOTE this does not use the myj.update(retry=True) logic as below
            #      because since this download is still healthy better to stay in normal loop
            warnings.warn('Cannot get status from Pervellam server, will retry in a minute...')
            continue
        # 'stopped' here means a force-stop already flipped the status (issue #39);
        # treat it like a stopreq so the still-running download is actually killed.
        if pjs in ("stopreq", "stopped"):
            print('Recieved stop request...')
            myd.stop()
            print('Job stopped!')
            file_info = myd.file_info()
            file_info['status'] = 'stopped'
            myj.update(file_info, retry=True)
            return file_info
        file_info = myd.file_info()
        if not myd.status():
            print('Job stopped organically!')
            myd.close()
            # TODO indicate 'failed' if nonzero or file missing etc
            file_info['status'] = 'ended'
            myj.update(file_info, retry=True)
            return file_info
        try:
            job_info = myj.update(file_info)
        except pervellam_client.requests.exceptions.RequestException:
            # NOTE this does not use the myj.update(retry=True) logic as above
            #      because since this download is still healthy better to stay in normal loop
            warnings.warn('Cannot update Pervellam server, will retry in a minute...')
            continue


def cdul_wrapper(server, dler, datadir, bucket):
    """Put in a specific directory and upload to OI"""
    cwd = os.getcwd()
    print(f'Worker {dler} looking for jobs...')
    myp = pervellam_client.Pervellam(server, dler)
    myj = myp.assign_job()
    if not myj:
        print('No jobs found')
        return
    newpath = pathlib.Path(tempfile.mkdtemp(prefix=f"{dler}-{myj.job_id}-",
                                            dir=datadir))
    os.chdir(newpath)
    file_info = run_one(dler, myj)
    if not file_info['fname']:
        warnings.warn('no file to upload')
        os.chdir(cwd)
        return
    info_json = None
    for pij in newpath.iterdir():
        if tuple(pij.suffixes) == ('.info', '.json'):
            info_json = pij
    assert info_json
    assert info_json.name != file_info['fname']
    info_json_data = dlpmeta.DLPMetaData(from_file=info_json, partial=True)
    media_file = info_json_data.get_media_file()
    assert media_file != info_json
    assert media_file.name == file_info['fname']
    info_json_data.add_lpm(LPM_LIB)
    oi_file = info_json_data.upload(oiclient.get_obj_idx_env(), bucket)
    myj.update({'fname': oi_file.oio.url + 'file/' + str(oi_file.uuid)})
    media_file.unlink()
    os.chdir(cwd)

def run_cli():
    """Basic CLI"""
    parser = argparse.ArgumentParser(description='Pervellam worker')
    parser.add_argument('server', help='Pervellam server URL')
    parser.add_argument('dler', help='Name of this worker')
    parser.add_argument('datadir')
    parser.add_argument('bucket')
    args = parser.parse_args()
    cdul_wrapper(args.server, args.dler, args.datadir, args.bucket)


if __name__ == '__main__':
    run_cli()
