#!/bin/sh
# Fully recreate the container, which is what gives the Apache master (and
# its ASLR base) a genuinely fresh process. The exploit's own worker
# rotation (crash-and-respawn the one prefork child over HTTP) happens
# inside this same process and does NOT get you a new ASLR base - that's
# chosen once when the master process itself starts. Use this between
# attempts you want the verify-exploit-poc skill to count as independent.
set -e
cd "$(dirname "$0")"
sh ./down.sh 2>/dev/null || true
sh ./up.sh
