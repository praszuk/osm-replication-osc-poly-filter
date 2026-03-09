FROM python:3.13

RUN apt-get update && apt-get install -y osm2pgsql curl
COPY requirements/requirements.txt /

RUN pip install -r requirements.txt
COPY replicate.sh schema.lua ./
