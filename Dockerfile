FROM python:3.13

ARG TESTS

RUN apt-get update && apt-get install -y osm2pgsql curl
COPY requirements/requirements.txt /requirements/requirements-test.txt /

RUN if [ "$TESTS" = "true" ]; then \
      pip install -r requirements-test.txt; \
    else \
      pip install -r requirements.txt; \
    fi
COPY schema.lua osc_poly_filter.py /
COPY scripts/ /scripts/
