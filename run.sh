#!/bin/bash
#
# This is a wrapper script to make passing the -e vars easier
#

function usage(){
   echo "Usage: ./run.sh -t <psql_target_ip> [image_name]"
}

while getopts ":t:" opt; do
   case $opt in
   t)
      PGIP="$OPTARG"
      ;;
   \?)
      echo "Invalid option: -$OPTARG" >&2
      usage
      exit 1
      ;;
   :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 1
      ;;
   esac
done

if [ -z "$PGIP" ]; then
   echo "Error: Missing tag (-t). Must supply PSQL target IP." >&2
   usage
   exit 1
fi

shift $((OPTIND -1))

podman run --net=host -it -v ./src:/rds:Z \
   -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
   -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
   -e PGPASSWORD=$TF_VAR_psql_password \
   -e PGIP=$PGIP \
   "${1:-rds-resize}" /bin/bash
