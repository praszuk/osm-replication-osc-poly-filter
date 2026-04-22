FROM debian:trixie AS osm2pgsql_builder

ARG OSM2PGSQL_VERSION=2.2.0

# libpotrace-dev \ (optional)
# libopencv-dev \  (optional)
# pandoc \ (optional)
RUN apt-get update && apt-get install -y \
    git  \
    make \
    cmake \
    g++ \
    libboost-dev \
    libexpat1-dev \
    zlib1g-dev \
    libbz2-dev \
    libpq-dev \
    libproj-dev \
    lua5.3 \
    liblua5.3-dev \
    nlohmann-json3-dev \
    libluajit-5.1-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/osm2pgsql-dev/osm2pgsql.git /src --branch ${OSM2PGSQL_VERSION} --single-branch
WORKDIR /src

RUN mkdir build && cd build && \
    cmake -D WITH_LUAJIT=ON .. && \
    make -j$(nproc) && \
    make install DESTDIR=/out

FROM python:3.13-slim-trixie

ARG TESTS

COPY --from=osm2pgsql_builder /out/usr/local/bin/osm2pgsql /usr/local/bin/osm2pgsql
# Install curl, postgresql-client and other deps are for osm2pgsql (pyosmium inside requirements.txt)
# To get versions you can use RUN ldd /usr/local/bin/osm2pgsql
RUN apt-get update && apt-get install -y  \
    curl \
    postgresql-client \
    libexpat1 \
    zlib1g \
    libbz2-1.0 \
    libpq5 \
    libproj25 \
    lua5.3 \
    liblua5.3 \
    libluajit-5.1-2

RUN osm2pgsql --version  # verify

COPY requirements/requirements.txt /requirements/requirements-test.txt /
RUN if [ "$TESTS" = "true" ]; then \
      pip install -r requirements-test.txt; \
    else \
      pip install -r requirements.txt; \
    fi

COPY scripts/ /scripts/

RUN ln -s /scripts/create.sh /usr/local/bin/create && ln -s /scripts/replicate.sh /usr/local/bin/replicate
