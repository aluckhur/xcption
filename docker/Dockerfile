# set base image (host OS)
FROM python:2
#FROM xcption:1
# apt update
RUN apt update
RUN python -m pip install --upgrade pip

WORKDIR ["/root"]
COPY requirments.txt ./

RUN apt update
RUN apt install -y curl
RUN apt install -y jq
RUN apt install -y rsync
RUN apt install -y nfs-common
RUN apt install -y unzip 

RUN pip2 install -r requirments.txt
RUN rm -rf /usr/bin/python
RUN ln -s /usr/local/bin/python2 /usr/bin/python

