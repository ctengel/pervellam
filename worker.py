#!/usr/bin/env python3

"""Worker or downloader code for Pervellam"""

import argparse
import subprocess
import datetime
import time
import warnings
import os
import pathlib
import json
import obj_idx.client
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
                'updated': ourfile[2]}


def run_one(dler, myj):
    """Check for a new job, assign, run, wait to finish or stop"""
    print(f'Assigned job {myj.job_id}; getting more details...')
    job_info = myj.get(retry=True)
    assert job_info["dler"] == dler
    myd = DLPJob(job_info["url"])
    print('Job commenced, doing initial update...')
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
            # NOTE this does not use the myj.update(retry=True) logic as below
            #      because since this download is still healthy better to stay in normal loop
            warnings.warn('Cannot get status from Pervellam server, will retry in a minute...')
            continue
        if pjs == "stopreq":
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

def read_info_json(filename):
    """Return data from a JSON file"""
    with open(filename, encoding="utf-8") as user_file:
        parsed_json = json.load(user_file)
    return parsed_json

def get_objidx():
    """Get objidx from environment

    (stolen from obj_idx.cli)"""
    oi_url = os.environ['OBJIDX_URL']
    oi_user = os.environ['OBJIDX_AUTH'].partition(':')[0]
    objidx = obj_idx.client.get_obj_idx(oi_url, oi_user)
    return objidx

# TODO - next 3 functions steal alot from OI yt - merge back into OI lib

def upload(objidx, metadata, filename, bucket, pretend=False, partial=False, library=None):
    """Upload a given file based on JSON metadata"""
    url = metadata.get('webpage_url')
    if not (url and url.startswith('http')):
        url = metadata.get('url')
    assert url.startswith('http')
    person = None
    media = None
    if library:
        person = metadata.get('uploader')
        if metadata.get('creator'):
            person = metadata.get('creator')
        if partial:
            assert person
            starttime = datetime.datetime.utcfromtimestamp(metadata['timestamp']).isoformat()
            media = f'live-{person}-{starttime}-{metadata.get("id")}'
        else:
            if person:
                media = f'vid-{person}-{metadata.get("id")}'
            else:
                media = metadata.get("id")
    print(filename, url, person, media)
    if pretend:
        return None
    flob = obj_idx.client.upload_metadata(filename,
                                          objidx,
                                          bucket=bucket,
                                          url=url,
                                          direct=False,
                                          partial=partial,
                                          ytdl_info=metadata,
                                          library=library,
                                          person=person,
                                          media=media)
    if not flob:
        warnings.warn(f"Possible conflict for {filename}; upload failed")
        return None
    print(flob.uuid)
    return flob

def cdul_wrapper(server, dler, datadir, bucket):
    """Put in a specific directory and upload to OI"""
    cwd = os.getcwd()
    print(f'Worker {dler} looking for jobs...')
    myp = pervellam_client.Pervellam(server, dler)
    myj = myp.assign_job()
    if not myj:
        print('No jobs found')
        return
    startpath = pathlib.Path(datadir)
    subdir_name = f"{dler}-{myj.job_id}"
    newpath = startpath.joinpath(subdir_name)
    newpath.mkdir()
    os.chdir(newpath)
    file_info = run_one(dler, myj)
    assert file_info['fname']
    info_json = None
    for pij in newpath.iterdir():
        if tuple(pij.suffixes) == ('.info', '.json'):
            info_json = pij
    assert info_json
    assert info_json.name != file_info['fname']
    info_json_data = read_info_json(info_json)
    ij_extension = info_json_data.get('ext')
    assert ij_extension
    base_file_name = info_json.removesuffix('.info.json')
    assert base_file_name != info_json
    media_file = base_file_name + "." + ij_extension
    assert media_file == file_info['fname']
    oi_file = upload(get_objidx(), info_json_data, media_file, bucket, partial=True, library='TWCH')
    myj.update({'fname': oi_file.oio.url + '/files/' + oi_file.fil_uuid})
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
