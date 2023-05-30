# RDS Resizing Automation
## Goals
We want to be able to easily downsize the volume of our RDS database.

The preliminary steps to take as per **#6434**:

> TODO: Check how to migrate users, roles and all that from one postgresql instance to another

1. Create new RDS instance
1. Make sure nothing is writing to the old RDS instance
    - Identify animal processes that are using RDS
    - Stop animals systemd services using RDS (see Bolt task manipulate_animal_services in README.md)

1. `pg_dump` from the old RDS
1. `pg_restore` to the new RDS
1. Point animals to new RDS
    - Add new RDS database hostname to Hiera
    - Deploy the change to the main branch of the Cloud in question (production/beta/staging)
    - Run Puppet agent on all animals (that use RDS)

> NOTE: Everything except #5 can be tested in staging-cloud.

## Podman
Podman is the container management tool used for this process.

### Requirements
- running a container requires host to be in a 'workon' virtual-environment

#### To build image

    ./build.sh [image_name]

#### To auto run python script in container image:

    podman run <image_name>

#### To attach to container for development, ensure in propper virtual env:

    (virtual-env) ./run.sh -t <PSQL_IP> [container_name]

#### To remove ALL containers after testing:

    podman rm -a

#### To remove image:

    podman rmi <container_name>

