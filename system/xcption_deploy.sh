#!/bin/bash
#
# This script is intendent to install xcption and Nomad 
# on Ubuntu 16.04 Xenial/CentOS/RH managed by SystemD

#can be server or client 

export TERM=xterm-256color
export DATACENTER_NAME=DC1
export DEBIAN_FRONTEND=noninteractive
#export MAX_NOMAD_ALLOCS=5000
export SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
export REPO_MOUNT_POINT=${SCRIPT_DIR}/xcp_repo
#export OS_RELEASE=`lsb_release -d`

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


if [ "$INSTALLTYPE" == "client" -a -z "$SERVERIP" ]; then
  echo "Server IP should be provided when installtion type is client"
  echo "usage: xcption_deploy.sh -r x.x.x.x:/xcp_repo -t server" 1>&2
  echo "or:" 1>&2
  echo "usage: xcption_deploy.sh -r x.x.x.x:/xcp_repo -t client -s <SERVERIP>" 1>&2
  exit 1
fi

#check if the computer is connected to the internet. 
#wget -q --spider http://google.com
nc -z -w 2 google.com 443 > /dev/null 2>&1
if [ $? -eq 0 ]; then
  export ONLINE=true    
  echo "This is ONLINE installation"
else
  export ONLINE=false
  echo "This is OFFLINE installation"
fi

if [ "$INSTALLTYPE" == "client" ]; then
  echo Server IP address: $SERVERIP 
fi

echo "Repo path: $XCPREPO Mount Point will be:${REPO_MOUNT_POINT}"

#set -x

#Bringing the Information
echo "Determining local IP address"
#LOCAL_IPV4=$(hostname --ip-address)
LOCAL_IPV4=$(ip route get 1.2.3.4 | awk '{print $7}')

if [[ $LOCAL_IPV4 == *127.0.0* ]]; then  
  echo "Error: host local IP address points to localhost ($LOCAL_IPV4)." >&2;
  echo "Please update the /etc/hosts file to use external IP for the host name." >&2;
  echo "After changing the /etc/hosts entry, validate using the command: 'hostname --ip-address' It should return the external IP of the host." >&2;
  exit 1;
fi

echo "Using ${LOCAL_IPV4} as IP address for nomad configuration"

#validate which installation utility exists in the system
export APT=`command -v apt`
export YUM=`command -v yum`

if [ -n "$YUM" ]; then
    yum -y update
    INST_APP="yum"
elif [ -n "$APT" ]; then
    apt -y update
    INST_APP="apt"  
else
    echo "Error: no path to apt or yum" >&2;
    exit 1;
fi

if [ $INST_APP == "yum" ]; then
  yum install -y epel-release
  #yum install -y ${SCRIPT_DIR}/epel-release-latest-7.noarch.rpm
  yum install -y python-devel.x86_64
  yum install -y libpqxx-devel.x86_64
fi

$INST_APP install -y apt-transport-https software-properties-common

$INST_APP install -y \
    ca-certificates \
    curl \
    jq \
    unzip \
    python3 \
    rsync \
    nfs-utils \
    python3-pip 


if [ "$ONLINE" == "true" ]; then
  pip3 install -r $SCRIPT_DIR/requirments.txt 
  # pip3 install python-nomad
  # pip3 install jinja2
  # pip3 install csv
  # pip3 install argparse
  # pip3 install logging
  # pip3 install pprint
  # pip3 install requests
  # pip3 install prettytable
  # pip3 install croniter
  # pip3 install hurry.filesize
  # pip3 install treelib
  # pip3 install flask
else
  mkdir -p /tmp/pip_unzip_loc
  unzip -o ${SCRIPT_DIR}/pipmodules.zip -d /tmp/pip_unzip_loc
  
  #pip3 install --no-index --find-links /tmp/pip_unzip_loc -r $SCRIPT_DIR/requirements.txt
  pip3 install /tmp/pip_unzip_loc/pip/certifi*
  pip3 install /tmp/pip_unzip_loc/pip/chardet*
  pip3 install /tmp/pip_unzip_loc/pip/typing_extensions*
  pip3 install /tmp/pip_unzip_loc/pip/zipp*
  pip3 install /tmp/pip_unzip_loc/pip/importlib_metadata*
  pip3 install /tmp/pip_unzip_loc/pip/click*
  pip3 install /tmp/pip_unzip_loc/pip/importlib_metadata-4.4.0-py3-none-any.whl
  pip3 install /tmp/pip_unzip_loc/pip/python_dateutil*
  pip3 install /tmp/pip_unzip_loc/pip/croniter*
  pip3 install /tmp/pip_unzip_loc/pip/dataclasses*
  pip3 install /tmp/pip_unzip_loc/pip/MarkupSafe*
  pip3 install /tmp/pip_unzip_loc/pip/Werkzeug*
  pip3 install /tmp/pip_unzip_loc/pip/itsdangerous*
  pip3 install /tmp/pip_unzip_loc/pip/Jinja2*
  pip3 install /tmp/pip_unzip_loc/pip/Flask*
  pip3 install /tmp/pip_unzip_loc/pip/future*
  pip3 install /tmp/pip_unzip_loc/pip/hurry.filesize*
  pip3 install /tmp/pip_unzip_loc/pip/idna*
  pip3 install /tmp/pip_unzip_loc/pip/MarkupSafe*
  pip3 install /tmp/pip_unzip_loc/pip/wcwidth*
  pip3 install /tmp/pip_unzip_loc/pip/prettytable*
  pip3 install /tmp/pip_unzip_loc/pip/urllib3*
  pip3 install /tmp/pip_unzip_loc/pip/requests*
  pip3 install /tmp/pip_unzip_loc/pip/python_nomad*
  pip3 install /tmp/pip_unzip_loc/pip/six*
  pip3 install /tmp/pip_unzip_loc/pip/treelib*
  rm -rf /tmp/pip_unzip_loc
fi

if [ "$ONLINE" == "true" ]; then
  #CHECKPOINT_URL="https://checkpoint-api.hashicorp.com/v1/check"
  #NOMAD_VERSION=$(curl -s "${CHECKPOINT_URL}"/nomad | jq .current_version | tr -d '"')

  #echo "Fetching Nomad for linux version ${NOMAD_VERSION} ..."
  #curl -s https://releases.hashicorp.com/nomad/${NOMAD_VERSION}/nomad_${NOMAD_VERSION}_linux_amd64.zip -o ${SCRIPT_DIR}/nomad.zip
  echo "Installing Nomad linux..."
  unzip -o ${SCRIPT_DIR}/nomad.zip -d ${SCRIPT_DIR}
  #echo "Fetching Nomad for windows version ${NOMAD_VERSION} ..."
  #curl -s https://releases.hashicorp.com/nomad/${NOMAD_VERSION}/nomad_${NOMAD_VERSION}_windows_amd64.zip -o ${SCRIPT_DIR}/../windows/nomad_windows.zip
  echo "Installing Nomad windows..."
  unzip -o ${SCRIPT_DIR}/../windows/nomad_windows.zip -d ${SCRIPT_DIR}/../windows
  echo "Installing rclone"
  curl https://rclone.org/install.sh | sudo bash
fi

if [ -f ${SCRIPT_DIR}/../windows/xcp_windows.zip.00 ]; then
  cat ${SCRIPT_DIR}/../windows/xcp_windows.zip.* > ${SCRIPT_DIR}/../windows/xcp_windows.zip
fi  
unzip -o ${SCRIPT_DIR}/../windows/xcp_windows.zip -d ${SCRIPT_DIR}/../windows


unzip -o ${SCRIPT_DIR}/nomad.zip -d /usr/local/bin
chmod +x /usr/local/bin/nomad

echo "Configuring Nomad"
mkdir -p /var/lib/nomad /etc/nomad.d

if [ "$INSTALLTYPE" = "server" ]; then

  cat << EOCCF >/etc/nomad.d/server.hcl
bind_addr = "0.0.0.0"
region             = "${DATACENTER_NAME}"
datacenter         = "${DATACENTER_NAME}"
data_dir           = "/var/lib/nomad/"
#log_level          = "DEBUG"
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
  gc_inode_usage_threshold = 90
  gc_disk_usage_threshold = 90
  options {
    "driver.raw_exec.enable" = "1"
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
#log_level          = "DEBUG"
leave_on_interrupt = true
leave_on_terminate = true
client {
  enabled       = true
  network_speed = 10
  servers = ["${SERVERIP}"]
  gc_inode_usage_threshold = 90
  gc_disk_usage_threshold = 90
  options {
    "driver.raw_exec.enable" = "1"
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

echo "Configuring XCP"
mkdir -p /opt/NetApp/xFiles/xcp

cat <<EONSU >/opt/NetApp/xFiles/xcp/xcp.ini
[xcp]
catalog = ${XCPREPO}
EONSU

if [ -f ${SCRIPT_DIR}/license ]; then
  echo "Existing licensefile found."
  echo "Coping ${SCRIPT_DIR}/license to /opt/NetApp/xFiles/xcp/license"
  cp ${SCRIPT_DIR}/license /opt/NetApp/xFiles/xcp/license
fi 

cat <<EONSU > /etc/sysctl.conf
net.core.rmem_default = 1342177
net.core.rmem_max = 16777216
net.core.wmem_default = 1342177
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 1342177 16777216
net.ipv4.tcp_wmem = 4096 1342177 16777216
net.core.netdev_max_backlog = 300000
net.ipv4.tcp_fin_timeout = 10
EONSU

sysctl -p

if [ -f ${SCRIPT_DIR}/xcp.zip.00 ]; then
  cat ${SCRIPT_DIR}/xcp.zip.* > ${SCRIPT_DIR}/xcp.zip
fi

if [ -f ${SCRIPT_DIR}/xcp.zip ]; then
  unzip -o ${SCRIPT_DIR}/xcp.zip
  chmod +x xcp
  mv -f xcp /usr/local/bin/xcp
fi


mkdir -p ${SCRIPT_DIR}/xcp_repo/jobs
chmod 770 ${SCRIPT_DIR}/xcp_repo
chmod 770 ${SCRIPT_DIR}/xcp_repo/jobs

if [ ! -L "${SCRIPT_DIR}/../webtemplates/nomadcache" ]; then
  ln -s ${SCRIPT_DIR}/xcp_repo/nomadcache ${SCRIPT_DIR}/../webtemplates/nomadcache
fi

if grep -q "${REPO_MOUNT_POINT}" "/etc/fstab"
then
  echo "${REPO_MOUNT_POINT} already in fstab" 
else
  echo "${XCPREPO} ${REPO_MOUNT_POINT} nfs  defaults,vers=3 0 0" >> /etc/fstab
fi

mount ${REPO_MOUNT_POINT}

if grep -qs ${REPO_MOUNT_POINT} /proc/mounts; then
  echo "XCP repo:${REPO_MOUNT_POINT} is mounted."
  if [ ! -d "${REPO_MOUNT_POINT}/cloudsync" ]; then
    mkdir ${REPO_MOUNT_POINT}/cloudsync
  fi
  if [ "$INSTALLTYPE" == "server" ]; then
    cp -r ${SCRIPT_DIR}/../cloudsync/* ${REPO_MOUNT_POINT}/cloudsync
  fi
  if [ ! -d "${REPO_MOUNT_POINT}/excludedir" ]; then
    mkdir ${REPO_MOUNT_POINT}/excludedir
  fi
  if [ ! -d "${REPO_MOUNT_POINT}/rclone" ]; then
    mkdir ${REPO_MOUNT_POINT}/rclone
  fi  
  if [ "$INSTALLTYPE" == "server" ]; then
    cp -r ${SCRIPT_DIR}/../rclone/* ${REPO_MOUNT_POINT}/rclone
  fi
  mkdir -p ${REPO_MOUNT_POINT}/xcplogs
  exit 0 
else
  echo "ERROR: could not mount XCP repo:${REPO_MOUNT_POINT}"
  exit 1
fi  
