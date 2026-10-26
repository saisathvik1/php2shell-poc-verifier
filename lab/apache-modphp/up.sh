#!/bin/sh
# Official php:8.4.26-apache image, single prefork worker, display_errors
# on. This matches the build php2shell-kit's offset extractor measured as
# zif_system=0x465370, zval_ptr_dtor=0x65eb60 (see README for how to
# reproduce that extraction yourself, live, against this exact container -
# do not trust those two numbers as a substitute for doing it).
set -e
cd "$(dirname "$0")"
docker rm -f p2s-apache-lab 2>/dev/null || true
docker run -d --name p2s-apache-lab \
  -p 127.0.0.1:18167:80 \
  -v "$PWD/webroot:/var/www/html:ro" \
  -v "$PWD/php.ini:/usr/local/etc/php/conf.d/zz-lab.ini:ro" \
  -v "$PWD/apache.conf:/etc/apache2/conf-enabled/zz-lab.conf:ro" \
  php:8.4.26-apache

echo "waiting for the lab to answer..."
i=0
while [ "$i" -lt 20 ]; do
  if curl -fs http://127.0.0.1:18167/index.php >/dev/null 2>&1; then
    echo "ready -> http://127.0.0.1:18167/index.php"
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done
echo "lab did not become ready in time" >&2
exit 1
