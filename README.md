# php2shell lab + PoC verifier

Tools built while reproducing a PHP ASLR-bypass RCE PoC locally in Docker, plus
a Claude Code skill that mechanically checks whether a downloaded
memory-corruption exploit genuinely leaks its coordinates at runtime or just
replays addresses the author happened to capture once in their own container.

> Authorized local testing only. Everything here talks to loopback Docker
> containers you control; nothing is pointed at a system you don't own or
> don't have written permission to test.

## What's in here

| Path | What it is |
|---|---|
| `lab/` | A disposable Docker lab: Alpine PHP 8.4.26 behind nginx, calibrated to match a specific CTF PoC's target. `up.sh` / `down.sh` / `restart-php.sh`. |
| `walkthrough.py` | A narrated wrapper around that PoC - imports its real functions (unmodified) and prints out what each stage is doing: the memory-exhaustion request, the leaked addresses, the forged structure's hex dump, the final response. Built for learning the exploit, not just running it. |
| `.claude/skills/verify-exploit-poc/` | A Claude Code skill: given a PoC + a lab that reproduces its target, drives a static scan, a dynamic cross-restart address comparison, and (where the PoC's code allows it) a corruption test, to tell a genuine live exploit from a dummy one that hardcodes ASLR addresses. |

## The lab

```bash
sh lab/up.sh              # bring up the Alpine PHP 8.4.26 + nginx lab on 127.0.0.1:18166
sh lab/restart-php.sh     # recreate just the PHP container (it segfaults after a successful run)
sh lab/down.sh            # tear everything down
```

`lab/up.sh` builds the lab from three small files it writes under `lab/public/`,
`lab/print-flag`, `lab/nginx.conf` - nothing in the lab itself depends on the
PoC it was calibrated against, so it's reusable as a template for other PHP
8.4.26/Alpine targets.

## Running the walkthrough

The PoC this was built against is
[KillaBoi/StealMyBitcoin-PoC](https://github.com/KillaBoi/StealMyBitcoin-PoC)
(not vendored here - it's someone else's repo with no license file). Clone it
yourself next to this project:

```bash
git clone https://github.com/KillaBoi/StealMyBitcoin-PoC
python3 -I walkthrough.py --url http://127.0.0.1:18166/php-version.php
```

`walkthrough.py` hard-codes the path to that clone at the top of the file -
adjust `POC_DIR` if you put it somewhere else. It only runs against
`127.0.0.1`/`localhost`, by design.

## The verify-exploit-poc skill

See [`.claude/skills/verify-exploit-poc/SKILL.md`](.claude/skills/verify-exploit-poc/SKILL.md)
for the full method. Short version: most public PoCs for ASLR-dependent bugs
have a "leak an address" step and a "use the address" step - the first one is
where authors most often cut corners, since it's easy to publish a PoC whose
leak is cosmetic and whose real coordinates are a constant that only matches
the one container image the author measured it against. The skill drives:

1. **Static scan** (`scripts/scan_source.py`) - flags hardcoded-looking
   address constants and whether they're ever reassigned from parsed network
   data.
2. **Dynamic cross-restart comparison** (`scripts/extract_addresses.py` +
   `scripts/compare_runs.py`) - runs the PoC several times against
   independently *recreated* target processes and checks whether the leaked
   values move the way real ASLR should, including a fixed-low-bit-suffix
   check for the page-offset fingerprint a real pointer leaves behind.
3. **Corruption test** - feeds the final exploit step a deliberately wrong
   address and checks whether it still reports success.

`references/worked-example.md` walks through all three checks against
`StealMyBitcoin-PoC` + `lab/`, including the single biggest pitfall
(comparing addresses across requests to a container that never actually
restarted gives a false "identical" result - worker processes keep their
ASLR base for as long as they stay alive).

The skill was also run, as a second test case, against
[kaaangumus/php2shell-kit](https://github.com/kaaangumus/php2shell-kit) (a
wrapper around [9bie/php2shell-bypass-aslr-exp](https://github.com/9bie/php2shell-bypass-aslr-exp)) -
neither is vendored here for the same licensing reason as above.

## Using the skill on your own PoC

Open this project in Claude Code with the skill installed (it's project-scoped
here, under `.claude/skills/`), then ask something like "verify whether this
PoC actually works" or "test this exploit for real" while pointing at the PoC
file and a lab that reproduces its target. The skill will set the rest up from
there - see its `SKILL.md` for what it needs from you first.
