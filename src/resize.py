#!/usr/local/bin/python3
# pyright: reportMissingImports=false, reportGeneralTypeIssues=false, reportMissingModuleSource=false

# NOTE: connection string: psql -h $PGIP db_name db_user
# TODO: convert to class object / major refactor

from subprocess import Popen, PIPE
import yaml
import psycopg2
import boto3
import sys
import logging
import argparse
import os

# Globals to be manipulated by functions
master_rds_address=''
psql_admin=''
config={}
aws_access_key_id=''
aws_secret_access_key=''
aws_default_region=''
psql_password=''

def get_args() -> dict:
    parser = argparse.ArgumentParser( prog='rds-resize',
                    description='Creates RDS instance and dumps/restores databases.',
                    epilog='Script will loop through databases \
                            and dump/copy data to newly created rds instance.')
    parser.add_argument('-t', '--test', action='store_true')

    return parser.parse_args()


def test_rds():
    config = get_config()
    db_items = config['databases']
    psql_admin = config['psql_admin']
    db_names = list(db_items.keys())
    master_rds_address = get_rds_address(config['master_rds_identifier'])
    new_rds_address = get_rds_address(config['new_rds_identifier'])
    print(f"MASTER: {master_rds_address}")
    print(f"NEWRDS: {new_rds_address}")
    conn = psycopg2.connect(
        host=master_rds_address,
        database='postgres',
        user=psql_admin,
        password=psql_password
    )
    nconn = psycopg2.connect(
        host=new_rds_address,
        database='postgres',
        user=psql_admin,
        password=psql_password
    )

    conn.set_session(readonly=True)
    nconn.set_session(readonly=True)

    cur = conn.cursor()
    ncur = nconn.cursor()

    print(f"{'='*5} (active connections old/new) {'='*5}")
    for db_name in db_names:
        count = get_con_count(cur, db_name)
        ncount = get_con_count(ncur, db_name)
        print(f"{db_name}: \t{count}/{ncount}")
    print(f"{'='*40}")

    cur.close()
    ncur.close()
    conn.close()
    nconn.close()

    print(f"{'='*8} (table count old/new) {'='*9}")
    for db_name in db_names:
        count = get_table_count(master_rds_address, db_name)
        ncount = get_table_count(new_rds_address, db_name)
        print(f"{db_name}: \t{count}/{ncount}")
    print(f"{'='*40}")


def get_table_count(host: str, db_name: str) -> int:
    conn = psycopg2.connect(
        host=host,
        database=db_name,
        user=psql_admin,
        password=psql_password
    )
    cur = conn.cursor()
    cur.execute(f"""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_type = 'BASE TABLE' AND table_schema = 'public';
        """)
    result = cur.fetchone()

    cur.close()
    conn.close()

    if result is not None:
        return result[0]
    return None


def get_config(yml_config: str = 'config.yaml') -> hash:
    with open(yml_config, 'r') as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    return data


def run_process(cmd: list[str], use_shell: bool = False):
    logging.debug(f'launching process with cmd: {cmd}')
    if use_shell:
        cmd = ' '.join(cmd)
    p = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=use_shell)
    stdout, stderr = p.communicate()
    if stdout:
        logging.info(stdout)
    if stderr:
        logging.error(stderr)
    exit_code = p.wait()
    if exit_code:
        logging.warning(f'process command {cmd} exited with {exit_code}')
    logging.debug('process closed')


def get_con_count(cur, db_name: str) -> int | None:
    cur.execute(f"""
            SELECT count(*) FROM pg_stat_activity
            WHERE datname = '{db_name}';
        """)
    result = cur.fetchone()
    if result is not None:
        return result[0]
    return None


def check_dbs_in_use(db_names: list[str]) -> bool:
    # Connect to the database
    db_in_use = False
    conn = psycopg2.connect(
        host=master_rds_address,
        database='postgres',
        user=psql_admin,
        password=psql_password
    )

    cur = conn.cursor()

    for db_name in db_names:
        count = get_con_count(cur, db_name)
        if count is not None:
            if count > 0:
                db_in_use = True
                logging.critical(f"ERROR: {db_name} in use!")
        else:
            logging.critical(f"Error - check_db_use: no result on cur.fetchone()")
            db_in_use = True

    # Close the cursor and connection
    cur.close()
    conn.close()

    return db_in_use


def dump_db(db_name: str, dump_file: str = ''):
    if not dump_file:
        dump_file = f'./dump/{db_name}.dump'

    if os.path.exists(dump_file):
        logging.warning(f'Dump file {dump_file} already exists! Using...')
        return
    logging.info(f"Dumping db {db_name} to {dump_file}...")
    cmd = [
        'pg_dump', '-U', psql_admin, '-h', master_rds_address, '-F', 'c', '-f', dump_file, db_name
    ]
    run_process(cmd)
    logging.debug(f"Finished dumping {db_name} to {dump_file}.")


def restore_db(db_name: str, new_rds_address: str, restore_file: str = ''):
    if not restore_file:
        restore_file = f'./dump/{db_name}.dump'
    logging.info(f'Restoring {db_name} db with {restore_file}...')
    if not os.path.exists(restore_file):
        logging.error(f'file {restore_file} does not exist!')
        return
    cmd_restore_db = [
        'pg_restore', '-U', psql_admin, '-h', new_rds_address, '-F', 'c',
        '--create', '-d', 'postgres', restore_file
    ]
    run_process(cmd_restore_db)
    logging.debug('Finished restoring')


def dump_globals(dump_file: str = './dump/globals.sql'):
    if os.path.exists(dump_file):
        logging.warning(f'Dump file {dump_file} already exists! Using...')
        return

    logging.info(f'Dumping Globals to {dump_file}...')
    cmd = [
        'pg_dumpall', '-U', psql_admin, '-h', master_rds_address, '-f', dump_file,
        '--no-role-passwords', '-g'
    ]
    run_process(cmd)
    logging.debug('Finished Dumping Globals')


def restore_globals(new_rds_address: str, restore_file: str = './dump/globals.sql'):
    logging.info(f'Restoring Globals from {restore_file}...')
    if not os.path.exists(restore_file):
        logging.error(f'file {restore_file} does not exist!')
        return

    cmd = [
        'psql', '-U', psql_admin, '-h', new_rds_address,
        '-d', 'postgres', '<', restore_file
    ]
    logging.debug(f"global restore cmd: {' '.join(cmd)}")
    run_process(cmd, True)
    logging.debug(f'global restore complete')


def restore_password(user: str, password: str, new_rds_address: str):
    logging.info(f'restoring {user} password')
    sql_reset = f"ALTER USER {user} WITH PASSWORD '{password}';"
    sql_login = f"ALTER ROLE {user} LOGIN;"
    cmd = [
        'psql', '-U', psql_admin, '-h', new_rds_address,
        '-d', 'postgres', '-c', sql_reset
    ]
    cmd2 = [
        'psql', '-U', psql_admin, '-h', new_rds_address,
        '-d', 'postgres', '-c', sql_login
    ]
    run_process(cmd)
    run_process(cmd2)
    logging.debug(f'password restore complete')


def rds_instance_exists(instance_name: str) -> bool:
    response = rds.describe_db_instances()
    for instance in response['DBInstances']:
        if instance['DBInstanceIdentifier'] == instance_name:
            logging.warning(f"RDS instance {instance_name} already exists!")
            return True
    return False


def get_rds_address(instance_name: str) -> str:
    result = rds.describe_db_instances(DBInstanceIdentifier=instance_name)
    rds_stats = result['DBInstances'][0]
    address = rds_stats['Endpoint']['Address']
    return address


def create_rds(db_identifier: str) -> str:
    """
    Create a new RDS instance and return the address.

    Args:
        db_identifier (str): Newly created rds identifier

    Returns:
        str: The rds endpoint address associated with the new instance
    """
    global master_rds_address
    allocated_storage = config['allocated_storage']
    max_allocated_storage = config['max_allocated_storage']
    master_db_identifier = config['master_rds_identifier']
    result = rds.describe_db_instances(DBInstanceIdentifier=master_db_identifier)
    master_db_stats = result['DBInstances'][0]
    master_rds_address = master_db_stats['Endpoint']['Address']
    print(f"Master RDS address: {master_rds_address}")
    logging.info(f"Master RDS address: {master_rds_address}")
    vpc_security_group_ids = []
    for group in master_db_stats['VpcSecurityGroups']:
        vpc_security_group_ids.append(group['VpcSecurityGroupId'])
    db_subnet_group_name = master_db_stats['DBSubnetGroup']['DBSubnetGroupName']
    new_db_stats = {
        'DBName': master_db_stats['DBName'],
        'AllocatedStorage': allocated_storage,
        'MaxAllocatedStorage': max_allocated_storage,
        'DBInstanceIdentifier': db_identifier,
        'DBInstanceClass': master_db_stats['DBInstanceClass'],
        'MasterUserPassword': psql_password,
        'DBSubnetGroupName': db_subnet_group_name,
        'Engine': master_db_stats['Engine'],
        'EngineVersion': master_db_stats['EngineVersion'],
        'MasterUsername': master_db_stats['MasterUsername'],
        'AvailabilityZone': master_db_stats['AvailabilityZone'],
        'PreferredMaintenanceWindow': master_db_stats['PreferredMaintenanceWindow'],
        # 'PreferredBackupWindow': master_db_stats['PreferredMaintenanceWindow'],
        'BackupRetentionPeriod': master_db_stats['BackupRetentionPeriod'],
        'VpcSecurityGroupIds': vpc_security_group_ids,
        'AutoMinorVersionUpgrade': master_db_stats['AutoMinorVersionUpgrade'],
        # 'TagList': master_db_stats['TagList'],
        # StorageEncrypted is not supported with db.t2.micro
        # 'StorageEncrypted': master_db_stats['StorageEncrypted'],
        'CopyTagsToSnapshot': master_db_stats['CopyTagsToSnapshot'],
        # MonitoringRoleARN is required when value is different than '0'
        # 'MonitoringInterval': master_db_stats['MonitoringInterval'],
        'DeletionProtection': master_db_stats['DeletionProtection'],
        'EnableCloudwatchLogsExports': master_db_stats['EnabledCloudwatchLogsExports']
    }
    logging.info('Creating db instance. This will take a while...')
    logging.debug(f'new db params: {new_db_stats}')
    rds.create_db_instance(**new_db_stats)

    # Wait for the instance to become available
    waiter = rds.get_waiter('db_instance_available')
    waiter.wait(DBInstanceIdentifier=db_identifier)
    logging.debug('Finished creating db instance')
    result = rds.describe_db_instances(DBInstanceIdentifier=db_identifier)
    new_db_stats = result['DBInstances'][0]
    logging.debug(f'Created db with stats: {new_db_stats}')
    return new_db_stats['Endpoint']['Address']


def main():
    global rds
    global config
    global psql_admin
    global master_rds_address

    global aws_access_key_id
    global aws_secret_access_key
    global aws_default_region
    global psql_password

    config = get_config()
    rds = boto3.client('rds')
    os.environ["AWS_ACCESS_KEY_ID"] = config['aws_access_key_id']
    os.environ["AWS_SECRET_ACCESS_KEY"] = config['aws_secret_access_key']
    os.environ["AWS_DEFAULT_REGION"] = config['aws_region']
    os.environ["PGPASSWORD"] = config['psql_password']
    db_items = config['databases']
    psql_admin = config['psql_admin']
    db_names = list(db_items.keys())

    logging.basicConfig(
        filename='resize.log',
        format='%(levelname)s: %(asctime)s %(message)s',
        datefmt='%m/%d/%Y %H:%M:%S',
        level=logging.INFO
    )
    if not rds_instance_exists(config['new_rds_identifier']):
        new_rds_address = create_rds(config['new_rds_identifier'])
        add_str = f"New RDS Address: {new_rds_address}"
        print(add_str)
        logging.info(add_str)
    else:
        if config['reuse_new_rds']:
            logging.warning(f"rds instance {config['new_rds_identifier']} exists, using...")
            new_rds_address = get_rds_address(config['new_rds_identifier'])
            master_rds_address = get_rds_address(config['master_rds_identifier'])
        else:
            logging.critical(f"rds instance {config['new_rds_identifier']} exists!")
            sys.exit()
    if not os.path.exists('./dump'):
        os.makedirs('./dump')
    dump_globals()
    restore_globals(new_rds_address)
    if check_dbs_in_use(db_names):
        print("Databases in-use. Check Logs.")
        sys.exit(1)
    for item in db_names:
        dump_db(item)
    for item in db_names:
        restore_db(item, new_rds_address)
        try:
            user = db_items[item]['user']
        except KeyError:
            user = item
        password = db_items[item]['password']
        restore_password(user, password, new_rds_address)
    logging.info('Fin')


if __name__ == '__main__':
    args = get_args()
    if args.test:
        print("WIP")
        # test_rds()
    else:
        main()
