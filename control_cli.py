#!/usr/bin/env python3

"""Simple interactive Pervellam controller"""

import argparse
import pervellam_client

def disp_status(svr):
    """Display status of active jobs"""
    for job in svr.list_jobs():
        print(f"{job['id']}\t{job['status']}\t{job['dler']}\t{job['url']}")

def input_act(svr):
    """Ask user for a choice to stop or start a job"""
    choice = input()
    if not choice:
        return
    if choice.isnumeric():
        svr.get_job(int(choice)).stop()
        return
    svr.new_job(choice)

def main_loop(svr):
    """Loop through display and change"""
    while True:
        disp_status(svr)
        input_act(svr)

def run_cli():
    """Basic CLI"""
    parser = argparse.ArgumentParser(description='Pervellam worker')
    parser.add_argument('server', help='Pervellam server URL')
    args = parser.parse_args()
    srv = pervellam_client.Pervellam(args.server)
    main_loop(srv)

if __name__ == '__main__':
    run_cli()
