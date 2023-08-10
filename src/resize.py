#!/usr/local/bin/python3
# pyright: reportMissingImports=false, reportGeneralTypeIssues=false, reportMissingModuleSource=false

# NOTE: connection string: psql -h $PGIP db_name db_user

from subprocess import Popen, PIPE
from shutil import rmtree
import yaml
import psycopg2
import boto3
import sys
import logging
import argparse
import os


class ResizeRDS:
    @staticmethod
    def get_config(cf: str = 'config.yaml') -> hash:
        with open(cf, 'r') as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
        return data


    @staticmethod
    def _get_rds_address(stats) -> str:
        return stats['Endpoint']['Address']


    def __init__(self, cf: str = "config.yaml"):
        self.args = self._get_args()
        self._setup_logging()
        c = self.get_config(cf)

        # Set EnvironmentVars for common command ussage
        os.environ["AWS_ACCESS_KEY_ID"]     = str(c['aws_access_key_id'])
        os.environ["AWS_SECRET_ACCESS_KEY"] = str(c['aws_secret_access_key'])
        os.environ["AWS_DEFAULT_REGION"]    = str(c['aws_region'])
        os.environ["PGPASSWORD"]            = str(c['psql_password'])

        self.new_rds_address = ''

        self.psql_password         = c['psql_password']
        self.databases             = c['databases']
        self.psql_admin            = c['psql_admin']
        self.master_rds_identifier = c['master_rds_identifier']
        self.new_rds_identifier    = c['new_rds_identifier']
        self.allocated_storage     = c['allocated_storage']
        self.max_allocated_storage = c['max_allocated_storage']
        self.master_db_identifier  = c['master_rds_identifier']
        self.reuse_new_rds         = c['reuse_new_rds']
        self.accounts              = c['accounts']


        self.rds = boto3.client('rds')
        self.master_rds_address = self._get_rds_address(self._get_rds_stats(self.master_db_identifier))


    def __del__(self):
        if hasattr(self, 'rds') and self.rds:
            logging.debug('closing rds client in __del__()')
            self.rds.close()


    def _get_args(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser( prog='rds-resize',
                        description='Creates RDS instance and dumps/restores databases.',
                        epilog='Script will loop through databases \
                                and dump/copy data to newly created rds instance.')
        parser.add_argument('-t', '--test', action='store_true')
        parser.add_argument('-v', '--verbose', action='store_true')
        parser.add_argument('-l', '--loglevel', choices=['debug', 'info', 'warning', 'error'],
                            default='info', help='Set the log level')

        return parser.parse_args()


    def _setup_logging(self):
        logger      = logging.getLogger('')
        log_level   = getattr(logging, self.args.loglevel.upper())
        log_format  = '%(levelname)s: %(asctime)s %(message)s'
        date_format = '%m/%d/%Y %H:%M:%S'
        formatter   = logging.Formatter(log_format, datefmt=date_format)

        file_handler = logging.FileHandler('resize.log')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


        if self.args.verbose:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)

        logger.setLevel(log_level)


    def _get_con_count(self, cur, db_name: str) -> int | None:
        cur.execute(f"""
                SELECT count(*) FROM pg_stat_activity
                WHERE datname = '{db_name}';
            """)
        result = cur.fetchone()
        if result is not None:
            return result[0]
        return None


    def _get_table_count(self, host: str, db_name: str) -> int:
        conn = psycopg2.connect(
            host=host,
            database=db_name,
            user=self.psql_admin,
            password=self.psql_password
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

    def _run_process(self, cmd: list[str], use_shell: bool = False):
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


    def _check_dbs_in_use(self, db_names: list[str]) -> bool:
        # Connect to the database
        db_in_use = False
        conn = psycopg2.connect(
            host=self.master_rds_address,
            database='postgres',
            user=self.psql_admin,
            password=self.psql_password
        )

        cur = conn.cursor()

        for db_name in db_names:
            count = self._get_con_count(cur, db_name)
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


    def _dump_db(self, db_name: str, dump_file: str = ''):
        if not dump_file:
            dump_file = f'./dump/{db_name}.dump'

        if os.path.exists(dump_file):
            logging.warning(f'Dump file {dump_file} already exists! Using...')
            return
        logging.info(f"Dumping db {db_name} to {dump_file}...")
        cmd = [
            'pg_dump', '-U', self.psql_admin, '-h', self.master_rds_address,
            '-F', 'c', '-f', dump_file, db_name
        ]
        logging.info(f"Dumping with cmd: {cmd}")
        self._run_process(cmd)
        logging.info(f"Finished dumping {db_name} to {dump_file}.")


    def _restore_db(self, db_name: str, restore_file: str = ''):
        if not restore_file:
            restore_file = f'./dump/{db_name}.dump'
        logging.info(f'Restoring {db_name} db with {restore_file}...')
        if not os.path.exists(restore_file):
            logging.error(f'file {restore_file} does not exist!')
            return
        cmd_restore_db = [
            'pg_restore', '-U', self.psql_admin, '-h', self.new_rds_address,
            '-F', 'c', '--create', '-d', 'postgres', restore_file
        ]

        logging.info(f"Restoring db with cmd: {cmd_restore_db}")
        self._run_process(cmd_restore_db)
        logging.info('Finished restoring')


    def _dump_globals(self, dump_file: str = './dump/globals.sql'):
        if os.path.exists(dump_file):
            logging.warning(f'Dump file {dump_file} already exists! Using...')
            return

        logging.info(f'Dumping Globals to {dump_file}...')
        cmd = [
            'pg_dumpall', '-U', self.psql_admin, '-h', self.master_rds_address,
            '-f', dump_file, '--no-role-passwords', '-g'
        ]
        logging.info(f'Dumping globals with cmd: {cmd}')
        self._run_process(cmd)
        logging.info('Finished Dumping Globals')



    def _restore_globals(self, restore_file: str = './dump/globals.sql'):
        logging.info(f'Restoring Globals from {restore_file}...')
        if not os.path.exists(restore_file):
            logging.error(f'file {restore_file} does not exist!')
            return

        cmd = [
            'psql', '-U', self.psql_admin, '-h', self.new_rds_address,
            '-d', 'postgres', '<', restore_file
        ]
        logging.info(f"global restore cmd: {' '.join(cmd)}")
        self._run_process(cmd, True)
        logging.info(f'global restore complete')


    def _restore_password(self, user: str, password: str):
        logging.info(f'restoring {user} password')
        sql_reset = f"ALTER USER {user} WITH PASSWORD '{password}';"
        sql_login = f"ALTER ROLE {user} LOGIN;"
        cmd = [
            'psql', '-U', self.psql_admin, '-h', self.new_rds_address,
            '-d', 'postgres', '-c', sql_reset
        ]
        cmd2 = [
            'psql', '-U', self.psql_admin, '-h', self.new_rds_address,
            '-d', 'postgres', '-c', sql_login
        ]


        logging.info(f"Restore password cmd-1: {cmd}")
        self._run_process(cmd)
        logging.info(f"Restore password cmd-2: {cmd2}")
        self._run_process(cmd2)
        logging.info(f'Restoring password complete')


    def _rds_instance_exists(self, instance_name: str) -> bool:
        response = self.rds.describe_db_instances()
        for instance in response['DBInstances']:
            if instance['DBInstanceIdentifier'] == instance_name:
                logging.warning(f"RDS instance {instance_name} already exists!")
                return True
        return False


    def _get_rds_stats(self, id: str):
        r = self.rds.describe_db_instances(DBInstanceIdentifier=id)
        return r['DBInstances'][0]


    def create_rds(self) -> str:
        master_db_stats = self._get_rds_stats(self.master_rds_identifier)

        logging.info(f"Master RDS address: {self.master_rds_address}")
        vpc_security_group_ids = []
        for group in master_db_stats['VpcSecurityGroups']:
            vpc_security_group_ids.append(group['VpcSecurityGroupId'])
        db_subnet_group_name = master_db_stats['DBSubnetGroup']['DBSubnetGroupName']
        new_db_stats = {
            'DBName': master_db_stats['DBName'],
            'AllocatedStorage': self.allocated_storage,
            'MaxAllocatedStorage': self.max_allocated_storage,
            'DBInstanceIdentifier': self.new_rds_identifier,
            'DBInstanceClass': master_db_stats['DBInstanceClass'],
            'MasterUserPassword': self.psql_password,
            'DBSubnetGroupName': db_subnet_group_name,
            'Engine': master_db_stats['Engine'],
            'EngineVersion': master_db_stats['EngineVersion'],
            'StorageEncrypted': master_db_stats['StorageEncrypted'],
            'MasterUsername': master_db_stats['MasterUsername'],
            'AvailabilityZone': master_db_stats['AvailabilityZone'],
            'PreferredMaintenanceWindow': master_db_stats['PreferredMaintenanceWindow'],
            'BackupRetentionPeriod': master_db_stats['BackupRetentionPeriod'],
            'VpcSecurityGroupIds': vpc_security_group_ids,
            'AutoMinorVersionUpgrade': master_db_stats['AutoMinorVersionUpgrade'],
            'CopyTagsToSnapshot': master_db_stats['CopyTagsToSnapshot'],
            'DeletionProtection': master_db_stats['DeletionProtection'],
            'EnableCloudwatchLogsExports': master_db_stats['EnabledCloudwatchLogsExports']
        }
        logging.info('Creating db instance. This will take a while...')
        logging.debug(f'new db params: {new_db_stats}')
        self.rds.create_db_instance(**new_db_stats)
        waiter = self.rds.get_waiter('db_instance_available')
        waiter.wait(DBInstanceIdentifier=self.new_rds_identifier)
        logging.info('Finished creating db instance')
        return self._get_rds_address(self._get_rds_stats(self.new_rds_identifier))


    def test_rds(self):
        db_names = self.databases
        if not self.master_rds_address:
            self.master_rds_address = self._get_rds_address(self._get_rds_stats(self.master_rds_identifier))
        if not self.new_rds_address:
            self.new_rds_address = self._get_rds_address(self._get_rds_stats(self.new_rds_identifier))

        logging.info(f"MASTER: {self.master_rds_address}")
        logging.info(f"NEWRDS: {self.new_rds_address}")
        conn = psycopg2.connect(
            host=self.master_rds_address,
            database='postgres',
            user=self.psql_admin,
            password=self.psql_password
        )
        nconn = psycopg2.connect(
            host=self.new_rds_address,
            database='postgres',
            user=self.psql_admin,
            password=self.psql_password
        )

        conn.set_session(readonly=True)
        nconn.set_session(readonly=True)

        cur = conn.cursor()
        ncur = nconn.cursor()

        logging.info(f"{'='*5} (active connections old/new) {'='*5}")
        for db_name in db_names:
            count = self._get_con_count(cur, db_name)
            ncount = self._get_con_count(ncur, db_name)
            logging.info(f"{db_name}: \t{count}/{ncount}")
        logging.info(f"{'='*40}")

        cur.close()
        ncur.close()
        conn.close()
        nconn.close()

        logging.info(f"{'='*8} (table count old/new) {'='*9}")
        for db_name in db_names:
            count = self._get_table_count(self.master_rds_address, db_name)
            ncount = self._get_table_count(self.new_rds_address, db_name)
            logging.info(f"{db_name}: \t{count}/{ncount}")
        logging.info(f"{'='*40}")


    def run(self, run_test: bool = True):
        db_names = self.databases

        if self._check_dbs_in_use(db_names):
            logging.critical("Databases in-use. Check Logs.")
            sys.exit(1)

        if os.path.exists('./dump'):
            rmtree('./dump', ignore_errors=True)
        os.makedirs('./dump')

        if not self._rds_instance_exists(self.new_rds_identifier):
            self.new_rds_address = self.create_rds()
            logging.info(f"New RDS Address: {self.new_rds_address}")
        else:
            if self.reuse_new_rds:
                logging.warning(f"rds instance {self.new_rds_identifier} exists, using...")
                self.new_rds_address = self._get_rds_address(self._get_rds_stats(self.new_rds_identifier))
            else:
                logging.critical(f"rds instance {self.new_rds_identifier} exists!")
                sys.exit(1)


        self._dump_globals()
        self._restore_globals()


        for item in db_names:
            self._dump_db(item)

        for item in db_names:
            self._restore_db(item)
            for user in self.accounts:
                password = self.accounts[user]
                self._restore_password(user, password)
        if run_test:
            self.test_rds()

        logging.info('Finished')


if __name__ == '__main__':
    r = ResizeRDS()
    args = r.args
    if args.test:
        r.test_rds()
    else:
        r.run()
