#!/bin/sh
cd "$(dirname "$0")"
docker network create ctf-cross-net
docker run -d --name ctf-cross-php --network ctf-cross-net \
  --read-only --tmpfs /tmp:rw,size=32m,mode=1777 --memory 1g \
  -v "$PWD/public:/app:ro" \
  -v "$PWD/print-flag:/usr/local/bin/print-flag:ro" \
  -e PHP_CLI_SERVER_WORKERS=4 \
  php:8.4.26-fpm-alpine3.23 php -S 0.0.0.0:8000 -t /app
docker run -d --name ctf-cross-nginx --network ctf-cross-net \
  -p 127.0.0.1:18166:80 \
  -v "$PWD/nginx.conf:/etc/nginx/nginx.conf:ro" \
  nginx:1.27-alpine
