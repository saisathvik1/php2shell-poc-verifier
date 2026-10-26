#!/usr/bin/env bash
# Install (or remove) the verify-exploit-poc Claude Code skill from this repo.
#
# By default it installs to ~/.claude/skills/, which makes the skill
# available to Claude Code in every project for your user - not just when
# you happen to have this repo open. Use --project to scope it to one
# project instead (same effect as cloning this repo there, but without
# bringing the lab/walkthrough files along).
set -euo pipefail

SKILL_NAME="verify-exploit-poc"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/.claude/skills/$SKILL_NAME"

usage() {
  cat <<EOF
Install the $SKILL_NAME Claude Code skill.

Usage:
  $0                      Install to ~/.claude/skills/   (every project, this user)
  $0 --project <dir>      Install to <dir>/.claude/skills/  (that project only)
  $0 --symlink            Symlink instead of copying (stays in sync with this repo;
                           breaks if you move or delete this repo)
  $0 --uninstall          Remove the installed skill (respects --project)
  $0 -h | --help          Show this help
EOF
}

mode=copy
target_base="$HOME/.claude/skills"
action=install

while [ $# -gt 0 ]; do
  case "$1" in
    --project)
      [ $# -ge 2 ] || { echo "--project needs a directory argument" >&2; exit 1; }
      target_base="$2/.claude/skills"
      shift 2
      ;;
    --symlink) mode=symlink; shift ;;
    --uninstall) action=uninstall; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

target="$target_base/$SKILL_NAME"

if [ "$action" = uninstall ]; then
  if [ -e "$target" ] || [ -L "$target" ]; then
    rm -rf "$target"
    echo "Removed $target"
  else
    echo "Nothing installed at $target"
  fi
  exit 0
fi

if [ ! -d "$SOURCE" ]; then
  echo "Skill source not found at $SOURCE - run this script from inside the repo." >&2
  exit 1
fi

if [ -e "$target" ] || [ -L "$target" ]; then
  echo "$target already exists - run with --uninstall first if you want to replace it." >&2
  exit 1
fi

mkdir -p "$target_base"

if [ "$mode" = symlink ]; then
  ln -s "$SOURCE" "$target"
  echo "Symlinked $target -> $SOURCE"
else
  cp -r "$SOURCE" "$target"
  echo "Copied $SOURCE -> $target"
fi

echo
echo "Installed. Claude Code will offer it as the 'verify-exploit-poc' skill."
echo "Restart any already-running Claude Code session to pick it up."
