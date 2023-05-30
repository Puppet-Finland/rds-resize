# Note: contains python 3.11.2
FROM docker.io/library/python:slim-buster

# These are used within the resize script
ENV AWS_ACCESS_KEY_ID ''
ENV AWS_SECRET_ACCESS_KEY ''
ENV PGPASSWORD ''
ENV PGIP ''

# Update and install postgresql 11.19
RUN apt-get update && \
    apt-get install -y \
    postgresql-client-11 \
    vim

RUN pip3 install boto3

VOLUME ["/rds"]

COPY ./src/resize.py /rds/resize.py

CMD ["python3", "/rds/resize.py"]
