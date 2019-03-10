#!/bin/bash
#
# This script is intendent to install both Consul and Nomad clients
# on Ubuntu 16.04 Xenial managed by SystemD

set -x
export INSTALLTYPE=server
export SERVERIP=x.x.x.x
export TERM=xterm-256color
export DEBIAN_FRONTEND=noninteractive
export DATACENTER_NAME="DC1"


#Bringing the Information
echo "Determining local IP address"
LOCAL_IPV4=$(hostname --ip-address)
echo "Using ${LOCAL_IPV4} as IP address for configuration and anouncement"


apt-get update
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    software-properties-common \
    jq \
    unzip \
    python \
    rsync \
    git

git clone https://gitlab.com/haim.marko/xcption

CHECKPOINT_URL="https://checkpoint-api.hashicorp.com/v1/check"
NOMAD_VERSION=$(curl -s "${CHECKPOINT_URL}"/nomad | jq .current_version | tr -d '"')

cd /tmp/

echo "Fetching Nomad version ${NOMAD_VERSION} ..."
curl -s https://releases.hashicorp.com/nomad/${NOMAD_VERSION}/nomad_${NOMAD_VERSION}_linux_amd64.zip -o nomad.zip
echo "Installing Nomad version ${NOMAD_VERSION} ..."
unzip nomad.zip
chmod +x nomad
mv nomad /usr/local/bin/nomad

echo "Configuring Nomad"
mkdir -p /var/lib/nomad /etc/nomad.d

if [ "$INSTALLTYPE" = "server" ]; then

  cat << EOCCF >/etc/nomad.d/
bind_addr = "0.0.0.0"
region             = "${DATACENTER_NAME}"
datacenter         = "${DATACENTER_NAME}"
data_dir           = "/var/lib/nomad/"
log_level          = "DEBUG"
leave_on_interrupt = true
leave_on_terminate = true
server {
  enabled = true
  bootstrap_expect = 1
}
client {
  enabled       = true
  network_speed = 10
  servers = ["${LOCAL_IPV4}"]
  options {
    "driver.raw_exec.enable" = "1"
    "gc_max_allocs" = 5000
  }
}

advertise {
  http = "${LOCAL_IPV4}:4646"
  rpc  = "${LOCAL_IPV4}:4647"
  serf = "${LOCAL_IPV4}:4648"
}

EOCCF
fi

if [ "$INSTALLTYPE" = "agent" ]; then

  cat << EOCCF >/etc/nomad.d/
bind_addr = "0.0.0.0"
region             = "${DATACENTER_NAME}"
datacenter         = "${DATACENTER_NAME}"
data_dir           = "/var/lib/nomad/"
log_level          = "DEBUG"
leave_on_interrupt = true
leave_on_terminate = true
client {
  enabled       = true
  network_speed = 10
  servers = ["${LOCAL_IPV4}"]
  options {
    "driver.raw_exec.enable" = "1"
    "gc_max_allocs" = 5000
  }
}

advertise {
  http = "${LOCAL_IPV4}:4646"
  rpc  = "${LOCAL_IPV4}:4647"
  serf = "${LOCAL_IPV4}:4648"
}

EOCCF
fi

cat << EONSU >/etc/systemd/system/nomad.service
[Unit]
Description=nomad agent
Requires=network-online.target
After=network-online.target
[Service]
LimitNOFILE=65536
Restart=on-failure
ExecStart=/usr/local/bin/nomad agent -config /etc/nomad.d
KillSignal=SIGINT
RestartSec=5s
[Install]
WantedBy=multi-user.target
EONSU

systemctl daemon-reload
systemctl start nomad