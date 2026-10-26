#!/bin/sh
# A successful run of the exploit corrupts the PHP worker process on
# purpose (that's what running the forged pDestructor does), so the
# container often dies (exit 139) right after a working run. This just
# restarts the PHP container without touching nginx or the network.
cd "$(dirname "$0")"
docker rm -f ctf-cross-php 2>/dev/null
docker run -d --name ctf-cross-php --network ctf-cross-net \
  --read-only --tmpfs /tmp:rw,size=32m,mode=1777 --memory 1g \
  -v "$PWD/public:/app:ro" \
  -v "$PWD/print-flag:/usr/local/bin/print-flag:ro" \
  -e PHP_CLI_SERVER_WORKERS=4 \
  php:8.4.26-fpm-alpine3.23 php -S 0.0.0.0:8000 -t /app
