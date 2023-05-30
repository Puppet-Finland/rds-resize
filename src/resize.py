#!/usr/local/bin/python3
#
# NOTE: connection string: psql -h $PGIP database_name username

import subprocess
# pg_config binary is required to use this library
# import psycopg2
import boto3
import os

# Environment Vars loaded by podman
aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
psql_ip=os.getenv('PGIP')
psql_password=os.getenv('PGPASSWORD')
psql_admin="admin"


# Create an RDS client
# rds = boto3.client('rds', aws_access_key_id, aws_secret_access_key)

def check_db_in_use(db_name):
    pass
    # Connect to the database
    conn = psycopg2.connect(
        host=psql_ip,
        database=db_name,
        user=psql_admin,
        password=psql_password
    )

    # Create a cursor
    cur = conn.cursor()

    # Execute a query to check if the database is in use
    cur.execute("""
        SELECT count(*) FROM pg_stat_activity
        WHERE datname = 'mydatabase' AND state = 'active';
    """)
    result = cur.fetchone()[0]

    # Close the cursor and connection
    cur.close()
    conn.close()

    # Check the result
    if result > 0:
        print("The database is in use.")
    else:
        print("The database is not in use.")


def dump():
    # In this example, the -F c option tells pg_dump to output a custom-format archive,
    # and the -f backup_file.dump option specifies the name of the output file
    # The subprocess.call function is used to execute the command and redirect its
    # output to the specified file.
    cmd = [
        'pg_dump', '-U', 'username', '-h', 'hostname', '-F',
        'c', '-f', 'backup_file.dump', 'database_name'
    ]

    # Execute the command and redirect the output to a file
    subprocess.call(cmd)

# Create the RDS instance
def create_rds():
    # Specify the parameters for the RDS instance
    rds_specs = {
        'DBInstanceIdentifier': 'my-db-instance',
        'DBInstanceClass': 'db.t2.micro',
        'Engine': 'psql',
        'EngineVersion': '11.11',
        'MasterUsername': 'admin',
        'MasterUserPassword': 'password',
        'AllocatedStorage': 20,
        'DBSubnetGroupName': 'db-subnet-group',
        'AvailabilityZone': 'us-west-2'
    }


    rds.create_db_instance(**rds_specs)

    # Wait for the instance to become available
    waiter = rds.get_waiter('db_instance_available')
    waiter.wait(DBInstanceIdentifier=db_instance_name)

def main():
    print(f"Target IP: {psql_ip}")

if __name__ == '__main__':
    main()

