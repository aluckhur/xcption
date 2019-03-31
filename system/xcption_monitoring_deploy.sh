
#!/bin/bash
#
# This script is intendent to monitoring for xcption and Nomad 
# on Ubuntu 16.04 Xenial/CentOS/RH managed by SystemD

apt install -y python-dev libcairo2-dev libffi-dev build-essential



################################################################
wget https://dl.grafana.com/oss/release/grafana_6.0.2_amd64.deb
dpkg -i grafana_6.0.2_amd64.deb
systemctl daemon-reload
systemctl enable grafana-server
service grafana-server start

apt install build-essential libssl-dev libffi-dev python-dev

export PYTHONPATH="/opt/graphite/lib/:/opt/graphite/webapp/"
pip install --no-binary=:all: https://github.com/graphite-project/whisper/tarball/master
pip install --no-binary=:all: https://github.com/graphite-project/carbon/tarball/master
pip install --no-binary=:all: https://github.com/graphite-project/graphite-web/tarball/master

GRAPHITE_ROOT=/opt/graphite
PYTHONPATH=$GRAPHITE_ROOT/webapp; django-admin migrate --settings=graphite.settings --run-syncdb

chown nobody /opt/graphite/storage/graphite.db

pip install -y gunicorn
apt install -y nginx

cat << EOCCF >/etc/nginx/sites-available/graphite

upstream graphite {
    server 127.0.0.1:8080 fail_timeout=0;
}

server {
    listen 80 default_server;

    server_name HOSTNAME;

    root /opt/graphite/webapp;

    access_log /var/log/nginx/graphite.access.log;
    error_log  /var/log/nginx/graphite.error.log;

    location = /favicon.ico {
        return 204;
    }

    # serve static content from the "content" directory
    location /static {
        alias /opt/graphite/webapp/content;
        expires max;
    }

    location / {
        try_files $uri @graphite;
    }

    location @graphite {
        proxy_pass_header Server;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Scheme $scheme;
        proxy_connect_timeout 10;
        proxy_read_timeout 10;
        proxy_pass http://graphite;
    }
}

EOCCF

ln -s /etc/nginx/sites-available/graphite /etc/nginx/sites-enabled
rm -f /etc/nginx/sites-enabled/default


pushd /opt/graphite/conf
cp carbon.conf.example carbon.conf
cp storage-schemas.conf.example storage-schemas.conf
popd 	

#####################

apt remove -y build-essential graphite-web graphite-carbon python-dev apache2 libapache2-mod-wsgi libpq-dev python-psycopg2 
apt remove -y collectd collectd-utils

cp /usr/share/doc/graphite-carbon/examples/storage-aggregation.conf.example /etc/carbon/storage-aggregation.conf

cp /usr/share/graphite-web/apache2-graphite.conf /etc/apache2/sites-available
