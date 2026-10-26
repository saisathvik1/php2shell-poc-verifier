<?php
// Health/fingerprint endpoint. Apache + mod_php adds X-Powered-By itself
// (expose_php defaults On), which is what the exploit's version check reads.
header('Content-Type: text/plain');
echo 'PHP/', PHP_VERSION, "\n";
echo 'PID: ', getmypid(), "\n";
