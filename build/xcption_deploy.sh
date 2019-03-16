#!/bin/bash
#
# This script is intendent to install both Consul and Nomad clients
# on Ubuntu 16.04 Xenial managed by SystemD

#can be server or client 

export TERM=xterm-256color
export DEBIAN_FRONTEND=noninteractive
export MAX_NOMAD_ALLOCS=5000
export SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
export REPO_MOUNT_POINT=${SCRIPT_DIR}/xcp_repo
export OS_RELEASE=`lsb_release -d`


if [ "$EUID" -ne 0 ];then 
  echo "This script should run using sudo or root"
  exit 1
fi

while getopts “r:t:s:” opt; do
  case $opt in
    r) XCPREPO=$OPTARG ;;
    t) INSTALLTYPE=$OPTARG ;;
    s) SERVERIP=$OPTARG ;;
    \?)   echo "usage: xcption_deploy.sh -r x.x.x.x:/xcp_repo -t server" 1>&2
          echo "or:" 1>&2
          echo "usage: xcption_deploy.sh -r x.x.x.x:/xcp_repo -t client -s <SERVERIP>" 1>&2
          exit 1
  esac
done 

if [ "$INSTALLTYPE" == "client" -o "$INSTALLTYPE" == "server" ]; then
  echo Installation type: $INSTALLTYPE
else
  echo "-t should be server or client"
  echo "usage: xcption_deploy.sh -r x.x.x.x:/xcp_repo -t server" 1>&2
  echo "or:" 1>&2
  echo "usage: xcption_deploy.sh -r x.x.x.x:/xcp_repo -t client -s <SERVERIP>" 1>&2
  exit 1
fi

echo "Repo path: $XCPREPO Mount Point will be:${REPO_MOUNT_POINT}"

if [ "$INSTALLTYPE" == "client" -a -z "$SERVERIP" ]; then
  echo "Server IP should be provided when installtion type is client"
  echo "usage: xcption_deploy.sh -r x.x.x.x:/xcp_repo -t server" 1>&2
  echo "or:" 1>&2
  echo "usage: xcption_deploy.sh -r x.x.x.x:/xcp_repo -t client -s <SERVERIP>" 1>&2
  exit 1
fi

if [ "$INSTALLTYPE" == "client" ]; then
  echo Server IP address: $SERVERIP 
fi


if [[ $OS_RELEASE == *"buntu"* ]]; then 
  echo OS $OS_RELEASE
else
  echo "This script is desgnated to run on Ubunto only"
  exit 1
fi


exit 1

set -x




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
pip install croniter


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
	echo "${REPO_MOUNT_POINT} already in fstab" 
else
  echo "${XCPREPO} ${REPO_MOUNT_POINT} nfs  defaults,vers=3 0 0" >> $fstab
  mount ${SCRIPT_DIR}/xcp_repo
fi


   
