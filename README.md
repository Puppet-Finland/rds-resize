# RDS PostgreSQL resizing automation

## Purpose

RDS GP2 volumes can only increase in size. Disk space running out is *not* the
only or possibly even the main reason for increasing disk size; you get more
burst credits for your volume by having a bigger disk. So, if you have lots of
disk activity, you may need to increase the volume to avoid volume I/O from
choking. This increase expenditure and going back to a smaller disk later is
not supported by AWS.

The tools in this repository automate much of the RDS resizing process.

## Requirements

The main requirement is [Podman](https://podman.io/). You can run the resizing
script without Podman, but you need to make sure that your environment is set
up just right.

You can use the [rhel9-setup-rds-resize.sh](rhel9-setup-rds-resize.sh) to set
up an environment with Podman and rds-resize.

## Run Steps

## Create a configuration file

Create a *./src/config.yaml* file based on the example. The settings are as follows:

* *master_rds_identifier*: the name of the *old* RDS instance to get settings and databases from.
* *new_rds_identifier*: the name of the *new* RDS instance you want to create.
* *allocated_storage*: size of the volume allocated to the *new* RDS instance. If you feel the urge to run this script then this should be smaller than the old RDS instance's volume: increase volume size does not require this convoluted process.
* *max_allocated_storage*: the maximum allocated storage. This affects RDS automatic storage size increases only.
* *psql_admin*: name of the RDS admin user. All SQL operations run as this user.
* *reuse_new_rds*: use an existing *new* RDS instance, if present. Useful when debugging data dump/restore issues orwhen you get connection interruptions during the process and would otherwise have to start from scratch.
* *databases*: a list of databases to dump from the old database and restore to the new database. The key is the database name. If *user* is not defined, the script assumes that the user name matches the database name. You also need to define *password* for the database user as that can't be dumped and restored like normal data.
* *aws_access_key_id* AWS API key id.
* *aws_secret_access_key*: AWS API key.
* *aws_region*: default region for aws.

## Ensure that environment variables are set

It should be enough to use

    workon <virtualenv>

## Build the container image

You can build the container image with *build.sh*. You need to have the
*BOLT_ssh_key_file* and *EYAML_CONFIG* environment variables set for build.sh
to work: this should be the case if you're in the correct Python virtualenv.

    $ build.sh <container-image-name>

The container image name can be whatever you want.

## Get the endpoint for the old RDS instance

This can be done with

    $ aws rds describe-db-instances

or from the AWS Console.

## Ensure that RDS is reachable

Your RDS instance should not be publicly accessible in most cases. If that is
the case, you probably have a VPN set up. So, make sure your VPN connection is
up.

You can use netcat for example to test that your old RDS instance is reachable:

    $ nc -z -v -w3 <old-rds-endpoint>:5432
    Ncat: Version 7.93 ( https://nmap.org/ncat )
    Ncat: Connected to 10.10.10.200:5432.
    Ncat: 0 bytes sent, 0 bytes received in 0.26 seconds.

## Make sure that nothing is connected to the databases

The script checks whether any of the databases your dumping have active
connections and if so, it will stop. However, it is best to make sure that all
connections are closed before you even start the script. Here's a one-liner to
do it for a single database:

    PGPASSWORD=<rds-admin-password> psql -h <old-rds-instance-endpoint> postgres <rds-admin-user> -c "SELECT count(*) FROM pg_stat_activity WHERE datname = '<database>';"

You should get

     count
    -------
         0

in return if you successfully stopped all processes that used the database. If count is not 0, you have something still using the database. You can get the IP of that something with the following spell:

    PGPASSWORD=<rds-admin-password> psql -h <old-rds-instance-endpoint> postgres <rds-admin-user> -c "SELECT datname,client_addr FROM pg_stat_activity;"

If the offending IP belongs to a Linux machine you can locate the offending process fairly easily:

    $ netstat -a --program|grep postgres

Typically the connected process would be a system service or a container. In that case it would be best to gracefully stop it. Otherwise just kill it:

    $ kill <pid>
    $ kill -9 <pid>

Alternatively you can try to kill the connection from server side. For details see [this article](https://dataedo.com/kb/query/postgresql/kill-session).

Once all connections to the database are down you can proceed with running the script.

## Launch the RDS resizing container

Just do

    $ ./run.sh <container-image-name>

This gives you a terminal with a pre-built container  environment for working
with RDS and database dump/restore procedures. The *src* folder is mounted as a
volume on the container.

## Run the resize script

Inside the container do

    $ cd /rds
    $ ./resize.py

Resize logs will be written to *resize.log* (*/rds* in the container, *src* on
the host). It is recommended to tail the logs while resizing is in progress:

    $ tail -f ./src/resize.log

# Troubleshooting

If for whatever reason passwords did not get set correctly, you can manually
fix that from RDS console:

    ALTER USER myuser PASSWORD 'supersecret';
    ALTER ROLE myuser LOGIN;

Some of the other user properties might have issues and might require manual
intervention. For example:

    ALTER ROLE myuser NOINHERIT;

Repeat these for all RDS users that have issues.
