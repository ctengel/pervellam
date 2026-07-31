#!/usr/bin/env python3

"""Upload media the worker left behind, then delete the local media file.

For each per-job directory left under datadir, this finds the matching Pervellam
job and deletes its media file only once we are certain the media is safe in
ObjectIndex (OI): either the job's ``fname`` already points at OI (an http URL —
a bare filename there is just a progress snapshot and proves nothing), or we
upload the media ourselves first. This is exactly what a healthy worker run does
(see worker.cdul_wrapper), just after the fact.

Only media files are ever removed: directories and info-jsons are left alone, as
are active jobs, unknown/missing jobs, and media we cannot upload. Dirs with no
media left to act on are reported as a single count rather than one line each.

Jobs stuck in 'upload' status (download done, upload to OI interrupted) are
finished here too. Since a job the worker is *currently* uploading has that same
status, run this while the worker is idle to avoid a duplicate upload.
"""

import argparse
import os
import pathlib
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


def is_info_json(path):
    """True if path is a yt-dlp info-json (never deleted, never uploadable)."""
    return tuple(path.suffixes) == ('.info', '.json')


def dir_size(path, skip_info_json=False):
    """Total size in bytes of everything under path."""
    return sum(f.stat().st_size for f in path.rglob('*')
               if f.is_file() and not (skip_info_json and is_info_json(f)))


def find_media(path):
    """Return the media file in path that upload_dir would act on, or None.

    Mirrors what worker.upload_dir needs (an info-json naming a media file that
    is really there) without uploading, so --dry-run and a real run agree on
    what is actionable. Anything we cannot make sense of — no info-json, an
    unreadable one, a playlist — is None: there is nothing we can safely do.
    """
    info_json = None
    for pij in path.iterdir():
        if is_info_json(pij):
            info_json = pij
    if not info_json:
        return None
    try:
        media_file = dlpmeta.DLPMetaData(from_file=info_json, partial=True).get_media_file()
    except Exception:  # noqa: BLE001 - unreadable metadata means nothing to act on
        return None
    if media_file == info_json:
        return None
    # get_media_file gives a bare name when the info-json carries 'filename',
    # an absolute path otherwise; path / either one resolves correctly.
    media_file = path / media_file
    return media_file if media_file.exists() else None


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


def upload_and_unlink(path, job_id, job, bucket, status):
    """Upload path's media to OI, then delete just that file. Returns bytes freed.

    Any upload failure leaves everything on disk and the job in its current
    status, so the media is never lost and the next run can retry.
    """
    # for a stuck 'upload' the ended-vs-stopped distinction is long gone; use 'ended'
    final_status = status if status in TERMINAL_STATUSES else 'ended'
    cwd = os.getcwd()
    try:
        os.chdir(path)
        uploaded = worker.upload_dir(path, bucket, job, final_status)
    except Exception as exc:  # noqa: BLE001 - any failure must NOT delete
        warnings.warn(f'{path.name}: could not upload job {job_id} to OI ({exc}) — keeping')
        return 0
    finally:
        os.chdir(cwd)
    # upload_dir returns the media path it uploaded, bare name and all; join it
    # back onto path since we are no longer inside the dir (worker.py:216)
    media = path / uploaded
    size = media.stat().st_size
    media.unlink()
    print(f'{path.name}: uploaded to OI then deleted {media.name} ({size} bytes)')
    return size


def sweep_dir(path, dler, bucket, myp, dry_run):
    """Decide and (unless dry_run) act on one scratch dir.

    Returns (media bytes reclaimed, dirs counted as having no media to act on).
    """
    job_id = parse_job_id(path.name, dler)
    if job_id is None:
        return 0, 0  # not one of our scratch dirs
    job, info = fetch_job(myp, job_id)
    if info is None:
        warnings.warn(f'{path.name}: no job {job_id} on server — manual review, keeping')
        return 0, 0
    status = info.get('status')
    if status not in SWEEPABLE_STATUSES:
        print(f'{path.name}: job {job_id} is {status} (active) — keeping')
        return 0, 0
    media = find_media(path)
    if media is None:
        # A stranded .part, or bytes with no info-json: real space we cannot
        # upload and must not delete, so say so rather than counting it away.
        leftover = dir_size(path, skip_info_json=True)
        if leftover:
            warnings.warn(f'{path.name}: no uploadable media but {leftover} bytes '
                          'on disk — manual review, keeping')
            return 0, 0
        if status == 'upload':
            # the worker recorded an fname that is neither on disk nor in OI
            warnings.warn(f'{path.name}: job {job_id} is in upload status but has '
                          'no media — manual review, keeping')
            return 0, 0
        return 0, 1  # media already uploaded and unlinked, or never downloaded
    size = media.stat().st_size
    # Only an fname holding an OI URL proves the media is in OI: while
    # downloading, the worker PATCHes the bare local filename into fname.
    if str(info.get('fname') or '').startswith('http'):
        if dry_run:
            print(f'{path.name}: media in OI — would delete {media.name} ({size} bytes)')
        else:
            media.unlink()
            print(f'{path.name}: media in OI — deleted {media.name} ({size} bytes)')
        return size, 0
    # Swept job whose media never reached OI: upload first, then delete.
    if dry_run:
        print(f'{path.name}: job {job_id} not in OI — would upload then delete '
              f'{media.name} ({size} bytes)')
        return size, 0
    return upload_and_unlink(path, job_id, job, bucket, status), 0


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
        print(f'{skipped} dirs with no media — nothing to do')
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
