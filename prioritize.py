#!/usr/bin/env python3

"""Start and stop jobs based on availability and priority"""

import argparse
import random
import tw
import pervellam_client
import config
import stream_ml

def read_prifile(prifile):
    """Read a simple priorities file"""
    with open(prifile) as file:
        priorities = file.read().splitlines()
    return priorities

def reconcile(pvo, add, count=5, dry_run=False):
    """Given a Pervellam object and an ordered list of desired live channels
    (already capped at count), add the missing ones and stop the excess.

    Shared by the priority-file (level 2) and ML (level 3) modes.
    """
    print("Live:")
    for one in add:
        print(one)
    # TODO object orientate
    running = [(x["id"], x["url"].split('/')[-1]) for x in pvo.list_jobs()]
    print("Running:")
    for one in running:
        print(one[1])
    actual_add = [x for x in add if x not in [y[1] for y in running]]
    print("Add:")
    for job in actual_add:
        print(job)
        if not dry_run:
            pvo.new_job(config.BASE_URL + job)
    total = len(running) + len(actual_add)
    print("Remove:")
    if total > count:
        remove = total - count
        removed = 0
        for job in running:
            if job[1] in add:
                continue
            print(job[1])
            if not dry_run:
                pvo.get_job(job[0]).stop()
            removed = removed + 1
            if removed == remove:
                break

def prioritize(pvo, two, priorities, count=5, dry_run=False):
    """Keep the top `count` live channels from the priority file running"""
    add = []
    avail = [x['user_login'] for x in two.followed()]
    for pri in priorities:
        if pri in avail:
            add.append(pri)
            if len(add) == count:
                break
    reconcile(pvo, add, count, dry_run)

def ml_prioritize(pvo, two, count=5, dry_run=False):
    """Keep the top `count` live channels as ranked by the trained model running"""
    vectorizer, model = stream_ml.load_model(config.ML_MODEL)
    scored = [(stream_ml.rank_score(vectorizer, model, stream), stream)
              for stream in two.followed()]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    print("Ranked:")
    for score, stream in scored:
        print(stream['user_login'], round(score, 3))
    add = [stream['user_login'] for score, stream in scored[:count]]
    reconcile(pvo, add, count, dry_run)

def pri_naieve(pvo, priorities):
    running = [(x["id"], x["url"].split('/')[-1]) for x in pvo.list_jobs()]
    print("Running:")
    for one in running:
        print(one[1])
    actual_add = [x for x in priorities if x not in [y[1] for y in running]]
    print('Add-options')
    for one in actual_add:
        print(one)
    if not actual_add:
        return
    rando = random.choice(actual_add)
    print(f'Rando: {rando}')
    pvo.new_job(config.BASE_URL + rando)



def wrapper(srv, prifile, naieve=False, ml=False, dry_run=False):
    """Setup needed objects and call actual prioritize()"""
    pvo = pervellam_client.Pervellam(srv)
    if naieve:
        pri_naieve(pvo, read_prifile(prifile))
        return
    two = tw.Tw.from_config(config)
    if ml:
        ml_prioritize(pvo, two, config.MAX, dry_run)
    else:
        prioritize(pvo, two, read_prifile(prifile), config.MAX, dry_run)


def run_cli():
    """Basic CLI"""
    parser = argparse.ArgumentParser(description='Pervellam prioritizer')
    parser.add_argument('server', help='Pervellam server URL')
    parser.add_argument('prifile', nargs='?', help='Ordered priority file (not used with --ml)')
    parser.add_argument('-n', '--naieve', action='store_true', help='do not actually check status, just try to add')
    parser.add_argument('-m', '--ml', action='store_true', help='rank live streams with the trained model instead of a priority file')
    parser.add_argument('--dry-run', action='store_true', help='print the add/stop plan without changing the server')
    args = parser.parse_args()
    if not args.ml and not args.prifile:
        parser.error('prifile is required unless --ml is given')
    wrapper(args.server, args.prifile, args.naieve, args.ml, args.dry_run)

if __name__ == '__main__':
    run_cli()
