#!/bin/bash
#
# This is a wrapper script to make passing the -e vars easier
#
podman run --net=host --tz=local -it \
   -v ./src:/rds:Z \
   -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
   -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
   -e AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION \
   -e PGPASSWORD=$TF_VAR_psql_password \
   -e VENV=$VENV \
   "${1:-rds-resize}" /bin/bash
