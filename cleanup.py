#!/usr/bin/env python3

"""Reclaim leftover worker scratch directories, preserving media in OI first.

For each per-job directory left under datadir, this finds the matching Pervellam
job and only removes the directory once we are certain its media is safe in
ObjectIndex (OI): either the job's ``fname`` already points at OI (an http URL —
a bare filename there is just a progress snapshot and proves nothing), or we
upload the media ourselves first. Active jobs, unknown/missing jobs, and
directories we cannot upload are left untouched.

Jobs stuck in 'upload' status (download done, upload to OI interrupted) are
finished here too. Since a job the worker is *currently* uploading has that same
status, run this while the worker is idle to avoid a duplicate upload.

Dirs holding no media at all (yt-dlp exited before writing anything, so the job
ended with no fname) have nothing to preserve and nothing to upload; they are
left in place and reported as a single count rather than one line each.
"""

import argparse
import os
import pathlib
import shutil
import warnings

import obj_idx.dlp_lpm_meta as dlpmeta
import pervellam_client
import worker

TERMINAL_STATUSES = ('ended', 'stopped')
# 'upload' = download finished but the OI upload was interrupted (see worker.py)
SWEEPABLE_STATUSES = TERMINAL_STATUSES + ('upload',)


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


def nothing_to_preserve(path):
    """True only if we can positively establish path holds no media.

    Mirrors what worker.upload_dir needs (an info-json naming a media file that
    is really there) without uploading, so --dry-run and a real run agree on
    what is uploadable. Anything we cannot make sense of — bytes with no
    info-json, an unreadable info-json — returns False so it keeps going down
    the loud 'keeping' path for manual review.
    """
    if dir_size(path) == 0:
        return True  # not a byte was ever written
    info_json = None
    for pij in path.iterdir():
        if tuple(pij.suffixes) == ('.info', '.json'):
            info_json = pij
    if not info_json:
        return False
    try:
        media_file = dlpmeta.DLPMetaData(from_file=info_json, partial=True).get_media_file()
    except Exception:  # noqa: BLE001 - unreadable metadata deserves a look, not a tally
        return False
    # get_media_file gives a bare name when the info-json carries 'filename',
    # an absolute path otherwise; path / either one resolves correctly.
    return media_file == info_json or not (path / media_file).exists()


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
    """Decide and (unless dry_run) act on one scratch dir.

    Returns (bytes reclaimed, dirs skipped for having nothing to preserve).
    """
    job_id = parse_job_id(path.name, dler)
    if job_id is None:
        return 0, 0  # not one of our scratch dirs
    size = dir_size(path)
    job, info = fetch_job(myp, job_id)
    if info is None:
        warnings.warn(f'{path.name}: no job {job_id} on server — manual review, keeping')
        return 0, 0
    status = info.get('status')
    if status not in SWEEPABLE_STATUSES:
        print(f'{path.name}: job {job_id} is {status} (active) — keeping')
        return 0, 0
    # Only an fname holding an OI URL proves the media is in OI: while
    # downloading, the worker PATCHes the bare local filename into fname.
    if str(info.get('fname') or '').startswith('http'):
        if dry_run:
            print(f'{path.name}: in OI already — would delete ({size} bytes)')
        else:
            shutil.rmtree(path)
            print(f'{path.name}: in OI already — deleted ({size} bytes)')
        return size, 0
    # No media here, so there is nothing to upload and nothing at risk. Leave the
    # dir alone (it costs no space) and let the caller report these as a count.
    if nothing_to_preserve(path):
        if status == 'upload':
            # the worker recorded an fname that is neither on disk nor in OI
            warnings.warn(f'{path.name}: job {job_id} is in upload status but has '
                          'no media — manual review, keeping')
            return 0, 0
        return 0, 1
    # Swept job whose media never reached OI: upload first, then delete.
    if dry_run:
        print(f'{path.name}: job {job_id} not in OI — would upload then delete ({size} bytes)')
        return size, 0
    # for a stuck 'upload' the ended-vs-stopped distinction is long gone; use 'ended'
    final_status = status if status in TERMINAL_STATUSES else 'ended'
    cwd = os.getcwd()
    try:
        os.chdir(path)
        worker.upload_dir(path, bucket, job, final_status)
    except Exception as exc:  # noqa: BLE001 - any failure must NOT delete
        os.chdir(cwd)
        warnings.warn(f'{path.name}: could not upload job {job_id} to OI ({exc}) — keeping')
        return 0, 0
    os.chdir(cwd)
    shutil.rmtree(path)
    print(f'{path.name}: uploaded to OI then deleted ({size} bytes)')
    return size, 0


def cleanup(server, dler, datadir, bucket, dry_run=False):
    """Sweep every scratch dir under datadir."""
    myp = pervellam_client.Pervellam(server, dler)
    total = 0
    skipped = 0
    for path in sorted(pathlib.Path(datadir).iterdir()):
        if path.is_dir():
            reclaimed, nomedia = sweep_dir(path, dler, bucket, myp, dry_run)
            total += reclaimed
            skipped += nomedia
    if skipped:
        print(f'{skipped} dirs with nothing to preserve — skipped')
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
