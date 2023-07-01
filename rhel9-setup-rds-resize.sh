#!/bin/bash

git_dir="/home/ec2-user/rds-resize"

hostnamectl hostname rds-resize

sudo dnf update -y
sudo dnf install -y \
  git \
  tmux \
  podman \
  vim

git clone https://github.com/Puppet-Finland/rds-resize.git "$git_dir"

chown -R ec2-user:ec2-user "$git_dir"
