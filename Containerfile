# Note: contains python 3.11.2
FROM docker.io/library/python:slim-buster

# Update and install postgresql 15
RUN apt-get update && \
    apt-get install -y \
    wget \
    gnupg2 \
    gcc \
    ruby \
    vim \
    postgresql-common

RUN yes | /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh

RUN apt-get install -y \
    postgresql-client-15 \
    postgresql-server-dev-15

RUN pip3 install boto3 psycopg2 pyyaml

VOLUME ["/rds"]
WORKDIR /rds
