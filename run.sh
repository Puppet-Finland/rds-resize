#!/bin/bash
#
# This is a wrapper script to make passing the -e vars easier
#
podman run --net=host --tz=local -it \
   -v ./src:/rds:Z "${1:-rds-resize}" /bin/bash
