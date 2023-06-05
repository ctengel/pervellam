#!/usr/bin/env python3

"""Start and stop jobs based on availability and priority"""

import argparse
import random
import tw
import pervellam_client
import config

def read_prifile(prifile):
    """Read a simple priorities file"""
    with open(prifile) as file:
        priorities = file.read().splitlines()
    return priorities

def prioritize(pvo, two, priorities, count=5):
    """Given a Pervellam object and a Tw object, make sure our priorities are aligned"""
    add = []
    avail = [x['user_login'] for x in two.followed()]
    for pri in priorities:
        if pri in avail:
            add.append(pri)
            if len(add) == count:
                break
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
            pvo.get_job(job[0]).stop()
            removed = removed + 1
            if removed == remove:
                break

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



def wrapper(srv, prifile, naieve=False):
    """Setup needed objects and call actual prioritize()"""
    priorities = read_prifile(prifile)
    if not naieve:
        # TODO gotta be a better way
        two = tw.Tw(url=config.TW_URL,
                    client_id=config.TW_CLI,
                    app_access_token=config.TW_APT,
                    #user_access_token=config.TW_UST,
                    user_refresh_token=config.TW_URT,
                    login=config.TW_USR,
                    id_url=config.TW_IDU,
                    client_secret=config.TW_CLS)
    pvo = pervellam_client.Pervellam(srv)
    if naieve:
        pri_naieve(pvo, priorities)
    else:
        prioritize(pvo, two, priorities, config.MAX)


def run_cli():
    """Basic CLI"""
    parser = argparse.ArgumentParser(description='Pervellam prioritizer')
    parser.add_argument('server', help='Pervellam server URL')
    parser.add_argument('prifile', help='Ordered priority file')
    parser.add_argument('-n', '--naieve', action='store_true', help='do not actually check status, just try to add')
    args = parser.parse_args()
    wrapper(args.server, args.prifile, args.naieve)

if __name__ == '__main__':
    run_cli()
