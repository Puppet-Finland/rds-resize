# Note: contains python 3.11.2
FROM docker.io/library/python:slim-buster

# Update and install postgresql 11.19
RUN apt-get update && \
    apt-get install -y \
    wget \
    postgresql-client-11 \
    gcc \
    postgresql-server-dev-11 \
    ruby \
    vim

RUN pip3 install boto3 psycopg2 pyyaml

VOLUME ["/rds"]
WORKDIR /rds
