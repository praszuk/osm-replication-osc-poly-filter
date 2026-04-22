#!/bin/bash

docker compose -f docker-compose-test.yml down --volumes
docker compose -f docker-compose-test.yml build
docker compose -f docker-compose-test.yml up -d

until docker compose -f docker-compose-test.yml exec -t db bash -c "pg_isready -U \$POSTGRES_USER"; do
  sleep 1;
done

if [ "$#" -eq 0 ]; then
  pytest_args="tests"
else
  pytest_args="$*"
fi
docker compose -f docker-compose-test.yml run --rm -it test bash -c "PYTHONPATH=/src pytest -s -p no:cacheprovider ${pytest_args}"
test_status_code=$?

docker compose -f docker-compose-test.yml down --volumes
exit $test_status_code

