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
| `lab/stealmybitcoin/` | Disposable Docker lab: Alpine PHP 8.4.26 CLI server behind nginx, matching the CTF PoC below. |
| `lab/apache-modphp/` | Disposable Docker lab: official `php:8.4.26-apache` image, single prefork worker, matching the mod_php build the `php2shell-kit` example chain targets. |
| `walkthrough.py` | A narrated wrapper around that PoC - imports its real functions (unmodified) and prints out what each stage is doing: the memory-exhaustion request, the leaked addresses, the forged structure's hex dump, the final response. Built for learning the exploit, not just running it. |
| `.claude/skills/verify-exploit-poc/` | A Claude Code skill: given a PoC + a lab that reproduces its target, drives a static scan, a dynamic cross-restart address comparison, and (where the PoC's code allows it) a corruption test, to tell a genuine live exploit from a dummy one that hardcodes ASLR addresses. |

## The labs

Two targets, because the two example PoCs below need different server
shapes - a multi-worker PHP CLI server vs. a single-worker Apache mod_php
process - and the skill's dynamic check depends on restarting the right
thing for each.

**`lab/stealmybitcoin/`** - Alpine PHP 8.4.26 CLI server behind nginx:

```bash
sh lab/stealmybitcoin/up.sh              # -> 127.0.0.1:18166
sh lab/stealmybitcoin/restart-php.sh     # recreate just the PHP container (it segfaults after a successful run)
sh lab/stealmybitcoin/down.sh            # tear everything down
```

**`lab/apache-modphp/`** - official `php:8.4.26-apache`, one prefork worker:

```bash
sh lab/apache-modphp/up.sh               # -> 127.0.0.1:18167
sh lab/apache-modphp/restart.sh          # fully recreate (needed between independent runs - see the script's own comment on why)
sh lab/apache-modphp/down.sh
```

Neither lab depends on the PoC it happens to be calibrated for beyond the PHP
build and worker count - reusable as a template for other PHP 8.4.26 targets
of the same shape.

## Running the walkthrough

The PoC `walkthrough.py` narrates is
[KillaBoi/StealMyBitcoin-PoC](https://github.com/KillaBoi/StealMyBitcoin-PoC)
(not vendored here - it's someone else's repo with no license file). Clone it
next to this project and point `lab/stealmybitcoin/` at it:

```bash
git clone https://github.com/KillaBoi/StealMyBitcoin-PoC
sh lab/stealmybitcoin/up.sh
python3 -I walkthrough.py --url http://127.0.0.1:18166/php-version.php
```

By default `walkthrough.py` looks for that clone as a sibling directory next
to itself; pass `--poc-dir /path/to/clone` or set `$STEALMYBITCOIN_POC_DIR` if
you put it somewhere else. It only runs against `127.0.0.1`/`localhost`, by
design.

## Installing just the skill

If you don't want the lab/walkthrough files, only the skill:

```bash
./install-skill.sh                      # -> ~/.claude/skills/ (every project, this user)
./install-skill.sh --project /path/to/your/project   # that project only
./install-skill.sh --symlink            # symlink instead of copy, stays in sync with this repo
./install-skill.sh --uninstall          # remove it
```

Cloning this whole repo and opening it in Claude Code also works without
running anything - project-scoped skills under `.claude/skills/` are picked
up automatically.

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
`StealMyBitcoin-PoC` + `lab/stealmybitcoin/`, including the single biggest
pitfall (comparing addresses across requests to a container that never
actually restarted gives a false "identical" result - worker processes keep
their ASLR base for as long as they stay alive).

The skill was also run, as a second test case, against
[kaaangumus/php2shell-kit](https://github.com/kaaangumus/php2shell-kit) (a
wrapper around [9bie/php2shell-bypass-aslr-exp](https://github.com/9bie/php2shell-bypass-aslr-exp))
using `lab/apache-modphp/` - neither is vendored here for the same licensing
reason as above. That run came back static-clean and dynamically genuine
(one live RCE, with real heap corruption logged on every attempt) but with
low reproducibility on this host, due to the single-worker race being far
less forgiving than the CLI server's four-worker one - a good example of the
"inconclusive on repeatability, not a dummy" verdict the skill is built to
report honestly rather than round off in either direction.

## Using the skill on your own PoC

Open this project in Claude Code with the skill installed (it's project-scoped
here, under `.claude/skills/`), then ask something like "verify whether this
PoC actually works" or "test this exploit for real" while pointing at the PoC
file and a lab that reproduces its target. The skill will set the rest up from
there - see its `SKILL.md` for what it needs from you first.
