#!/bin/bash
while true; do
	~/pervellam/worker.py $1 $3
	sleep $2
done
