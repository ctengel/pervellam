#!/usr/bin/env python3

"""Reclaim leftover worker scratch directories, preserving media in OI first.

For each per-job directory left under datadir, this finds the matching Pervellam
job and only removes the directory once we are certain its media is safe in
ObjectIndex (OI): either the job's ``fname`` already points at OI, or we upload
the media ourselves first. Active jobs, unknown/missing jobs, and directories we
cannot upload are left untouched.
"""

import argparse
import os
import pathlib
import shutil
import warnings

import pervellam_client
import worker

TERMINAL_STATUSES = ('ended', 'stopped')


def parse_job_id(dirname, dler):
    """Return the job id encoded in a worker scratch dir name, or None.

    Dir names are ``f"{dler}-{job_id}-{random}"`` (see worker.cdul_wrapper).
    """
    prefix = f"{dler}-"
    if not dirname.startswith(prefix):
        return None
    head = dirname[len(prefix):].split('-', 1)[0]
    return int(head) if head.isdigit() else None


def dir_size(path):
    """Total size in bytes of everything under path."""
    return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())


def fetch_job(myp, job_id):
    """Return (job, info) for job_id, or (None, None) if it is gone/unreachable."""
    job = myp.get_job(job_id)
    try:
        return job, job.get()
    except pervellam_client.requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None, None
        warnings.warn(f'Cannot reach server for job {job_id}: {exc}')
        return None, None
    except pervellam_client.requests.exceptions.RequestException as exc:
        warnings.warn(f'Cannot reach server for job {job_id}: {exc}')
        return None, None


def sweep_dir(path, dler, bucket, myp, dry_run):
    """Decide and (unless dry_run) act on one scratch dir. Return bytes reclaimed."""
    job_id = parse_job_id(path.name, dler)
    if job_id is None:
        return 0  # not one of our scratch dirs
    size = dir_size(path)
    job, info = fetch_job(myp, job_id)
    if info is None:
        warnings.warn(f'{path.name}: no job {job_id} on server — manual review, keeping')
        return 0
    if info.get('status') not in TERMINAL_STATUSES:
        print(f'{path.name}: job {job_id} is {info.get("status")} (active) — keeping')
        return 0
    if info.get('fname'):
        if dry_run:
            print(f'{path.name}: in OI already — would delete ({size} bytes)')
        else:
            shutil.rmtree(path)
            print(f'{path.name}: in OI already — deleted ({size} bytes)')
        return size
    # Terminal job, not yet in OI: upload first, then delete.
    if dry_run:
        print(f'{path.name}: job {job_id} not in OI — would upload then delete ({size} bytes)')
        return size
    cwd = os.getcwd()
    try:
        os.chdir(path)
        worker.upload_dir(path, bucket, job)
    except Exception as exc:  # noqa: BLE001 - any failure must NOT delete
        os.chdir(cwd)
        warnings.warn(f'{path.name}: could not upload job {job_id} to OI ({exc}) — keeping')
        return 0
    os.chdir(cwd)
    shutil.rmtree(path)
    print(f'{path.name}: uploaded to OI then deleted ({size} bytes)')
    return size


def cleanup(server, dler, datadir, bucket, dry_run=False):
    """Sweep every scratch dir under datadir."""
    myp = pervellam_client.Pervellam(server, dler)
    total = 0
    for path in sorted(pathlib.Path(datadir).iterdir()):
        if path.is_dir():
            total += sweep_dir(path, dler, bucket, myp, dry_run)
    verb = 'would reclaim' if dry_run else 'reclaimed'
    print(f'{verb} {total} bytes')


def run_cli():
    """Basic CLI"""
    parser = argparse.ArgumentParser(description='Pervellam scratch-space cleanup')
    parser.add_argument('server', help='Pervellam server URL')
    parser.add_argument('dler', help='Name of the worker whose dirs to sweep')
    parser.add_argument('datadir')
    parser.add_argument('bucket', help='ObjectIndex bucket to upload pending media into')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would happen without changing anything')
    args = parser.parse_args()
    cleanup(args.server, args.dler, args.datadir, args.bucket, args.dry_run)


if __name__ == '__main__':
    run_cli()
