#!/bin/bash
#
# simple wrapper to build image
#

podman build --tag "${1:-rds-resize}" .

