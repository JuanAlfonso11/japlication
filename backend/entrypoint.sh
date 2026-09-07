#!/bin/sh
# Runs the schema up to date before the API accepts a single request, then
# hands off to whatever the image's CMD is (uvicorn in normal use, pytest or
# a one-off script for `docker compose run`).
#
# `set -e` matters here: if the migration step fails, the container must die
# rather than start uvicorn against a schema in an unknown state. A backend
# that serves wrong data is worse than one that visibly refuses to boot.
set -e

python -m app.scripts.migrate

exec "$@"
