#!/bin/bash
#
# This script is intendent to install both Consul and Nomad clients
# on Ubuntu 16.04 Xenial managed by SystemD

set -x

if [ $# -lt 2 ]
then
    echo "usage: xcption_deploy.sh XCP_REPO=x.x.x.x:/xcp_repo MODE=server"
    echo "or:"
    echo "usage: xcption_deploy.sh XCP_REPO=x.x.x.x:/xcp_repo MODE=client SERVER=<SERVERIP>"
fi
echo "The follwing arguments been provided:" "$@"

#can be server or client 
export INSTALLTYPE=client
export SERVERIP=10.68.65.60
export TERM=xterm-256color
export DEBIAN_FRONTEND=noninteractive
export DATACENTER_NAME="DC1"
export XCPREPO="10.68.65.67:/xcprepo"
export MAX_NOMAD_ALLOCS=5000
export SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"



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
    nfs-common

pip install python-nomad
pip install jinja2
pip install csv
pip install argparse
pip install logging
pip install pprint
pip install requests
pip install prettytable


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

  cat << EOCCF >/etc/nomad.d/server.hcl
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
    "gc_max_allocs" = ${MAX_NOMAD_ALLOCS}
  }
}

advertise {
  http = "${LOCAL_IPV4}:4646"
  rpc  = "${LOCAL_IPV4}:4647"
  serf = "${LOCAL_IPV4}:4648"
}

EOCCF
fi

if [ "$INSTALLTYPE" = "client" ]; then

  cat << EOCCF >/etc/nomad.d/client.hcl
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
  servers = ["${SERVERIP}"]
  options {
    "driver.raw_exec.enable" = "1"
    "gc_max_allocs" = ${MAX_NOMAD_ALLOCS}
  }
}

advertise {
  http = "${SERVERIP}:4646"
  rpc  = "${SERVERIP}:4647"
  serf = "${SERVERIP}:4648"
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
systemctl enable nomad
systemctl start nomad

echo "configurting xcp"
mkdir -p /opt/NetApp/xFiles/xcp

cat <<EONSU >/opt/NetApp/xFiles/xcp/xcp.ini
[xcp]
catalog = ${XCPREPO}
EONSU

cp ${SCRIPT_DIR}/xcp_license /opt/NetApp/xFiles/xcp/license
cp ${SCRIPT_DIR}/xcp /usr/local/bin

mkdir -p ${SCRIPT_DIR}/xcp_repo
chmod 770 ${SCRIPT_DIR}/xcp_repo

fstab=/etc/fstab

if grep -q "xcp_repo" "$fstab"
then
	echo "${SCRIPT_DIR}/xcp_repo already in fstab" 
else
  echo "${XCPREPO} ${SCRIPT_DIR}/xcp_repo nfs  defaults,vers=3 0 0" >> $fstab
  mount ${SCRIPT_DIR}/xcp_repo
fi


   
