#!/bin/bash
while true; do
	~/pervellam/worker.py $1 $3 $4 $5
	sleep $2
done
