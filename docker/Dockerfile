# set base image (host OS)
FROM python:3
RUN apt update
RUN python3 -m pip install --upgrade pip

WORKDIR ["/root"]
COPY requirments.txt ./

RUN apt update
RUN apt install -y curl
RUN apt install -y jq
RUN apt install -y rsync
RUN apt install -y nfs-common
RUN apt install -y unzip 

RUN python3 -m pip install -r requirments.txt

