#!/usr/bin/env python3

"""Worker or downloader code for Pervellam"""

import argparse
import subprocess
import datetime
import time
import warnings
import os
import pathlib
import shutil
import sys
import tempfile
import obj_idx.dlp_lpm_meta as dlpmeta
import obj_idx.client as oiclient
import pervellam_client
import config

WAIT_FOR_KILL = 200
LPM_LIB = 'TWCH'
DEFAULT_MIN_FREE_BYTES = 32 * 1024**3  # 32 GiB
MIN_FREE_ENV = 'WORKER_MIN_FREE_BYTES'


def check_free_space(datadir):
    """Exit non-zero if free space in datadir is below the configured minimum.

    Minimum (bytes) comes from the WORKER_MIN_FREE_BYTES env var, defaulting to
    32 GiB. A value of 0 disables the check.
    """
    min_free = int(os.environ.get(MIN_FREE_ENV, DEFAULT_MIN_FREE_BYTES))
    if min_free <= 0:
        return
    free = shutil.disk_usage(datadir).free
    if free < min_free:
        print(f'Refusing to claim job: only {free} bytes free in {datadir}, '
              f'need {min_free} (set {MIN_FREE_ENV}=0 to disable)')
        sys.exit(1)


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


def report_downloaded(myj, file_info, final_status):
    """Record that downloading is done: 'upload' status until media is in OI.

    A job only becomes 'ended'/'stopped' once its media is safely in OI (or
    there is nothing to upload), so an interrupted upload stays visible as
    'upload' instead of silently stranding the media (#42/#43).
    """
    file_info['status'] = 'upload' if file_info['fname'] else final_status
    myj.update(file_info, retry=True)
    return file_info, final_status


def run_one(dler, myj):
    """Check for a new job, assign, run, wait to finish or stop

    Returns (file_info, final_status): the last snapshot of the downloaded
    file and the terminal status ('ended'/'stopped') to record once the media
    is safely in OI.
    """
    print(f'Assigned job {myj.job_id}; getting more details...')
    job_info = myj.get(retry=True)
    assert job_info["dler"] == dler
    myd = DLPJob(job_info["url"])
    try:
        print('Job commenced, doing initial update...')
        job_info = myj.update({'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                               'updated': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                               'status': 'running'},
                              retry=True)
        print('Looping and waiting...')
        while True:
            if job_info["dler"] != dler:
                warnings.warn('Conflict dectected, self destructing...')
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
                return report_downloaded(myj, myd.file_info(), 'stopped')
            file_info = myd.file_info()
            if not myd.status():
                print('Job stopped organically!')
                myd.close()
                # TODO indicate 'failed' if nonzero or file missing etc
                return report_downloaded(myj, file_info, 'ended')
            try:
                job_info = myj.update(file_info)
            except pervellam_client.requests.exceptions.RequestException:
                # NOTE this does not use the myj.update(retry=True) logic as above
                #      because since this download is still healthy better to stay in normal loop
                warnings.warn('Cannot update Pervellam server, will retry in a minute...')
                continue
    finally:
        # never leave yt-dlp downloading detached if we bail out for any reason
        if myd.status():
            myd.stop()


def upload_dir(newpath, bucket, myj, final_status, expect_fname=None):
    """Upload the media in newpath to OI, then record its OI URL and
    final_status on the job in a single update.

    Returns the local media_file Path (caller deletes it). Raises if there is
    no info-json / media to upload (or the media is not the expect_fname the
    download reported), so callers can decline to delete on failure; the job
    then stays in 'upload' status rather than looking done.
    """
    info_json = None
    for pij in newpath.iterdir():
        if tuple(pij.suffixes) == ('.info', '.json'):
            info_json = pij
    if not info_json:
        raise RuntimeError(f'no info-json in {newpath}')
    info_json_data = dlpmeta.DLPMetaData(from_file=info_json, partial=True)
    media_file = info_json_data.get_media_file()
    if media_file == info_json:
        raise RuntimeError(f'no media besides info-json {info_json} in {newpath}')
    if expect_fname and media_file.name != expect_fname:
        raise RuntimeError(f'info-json names media {media_file.name} '
                           f'but download reported {expect_fname}')
    info_json_data.add_lpm(LPM_LIB)
    oi_file = info_json_data.upload(oiclient.get_obj_idx_env(), bucket)
    myj.update({'fname': oi_file.oio.url + 'file/' + str(oi_file.uuid),
                'status': final_status},
               retry=True)
    return media_file


def cdul_wrapper(server, dler, datadir, bucket):
    """Put in a specific directory and upload to OI"""
    check_free_space(datadir)
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
    try:
        file_info, final_status = run_one(dler, myj)
        if not file_info['fname']:
            warnings.warn('no file to upload')
            return
        try:
            media_file = upload_dir(newpath, bucket, myj, final_status,
                                    expect_fname=file_info['fname'])
        except Exception as exc:  # noqa: BLE001 - keep media, stay in 'upload'
            warnings.warn(f'could not upload job {myj.job_id} to OI ({exc}); '
                          'media kept on disk, job left in upload status for cleanup.py')
            sys.exit(1)
        media_file.unlink()
    finally:
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
