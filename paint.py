#!/usr/bin/env python3
"""Paint a message across the GitHub contribution graph -- and keep it there.

Each run wipes ``main`` and rebuilds it from scratch on an orphan branch:

  * ``ART_INTENSITY`` back-dated empty commits for every lit pixel of the text,
    forming the painted chain;
  * a "tooling" commit dated 2019 (older than the graph's one-year window, so
    invisible) after every lit day, carrying this repo's own files, each one
    merging that day's painted commits onto the previous tooling commit.

``main`` is pushed once per lit day, immediately after that day's commits are
built, instead of once at the very end. GitHub only reliably credits a push's
commits when it's small and incremental -- a single force-push introducing
the whole painted history at once (tens of thousands of commits, spanning a
year) gets silently under-counted, with only the newest few days ever
credited no matter how long you wait. Pushing day-by-day keeps every push the
size GitHub has always credited correctly for this repo.

The tooling commits are merges (two parents: that day's painted commit, and
the previous tooling commit) rather than a single commit stacked on top at
the end, for two reasons. First, ``main`` needs real files checked out at
*every* push, not just the last one -- otherwise a run that dies partway
through (a rejected push, a runner timeout) leaves `main` bare, which strips
the workflow file off the branch and silently kills the cron trigger with no
way to recover except a manual push. Second, keeping the painted
(empty-tree) chain's own commits independent of files_tree means editing
paint.py doesn't force a full repaint of already-credited history -- only
the tooling commits change. The chain is deterministic within a week, so a
re-run reproduces identical SHAs and every push becomes a no-op.

The art is anchored to *this week's Sunday* minus ``ART_END_GAP`` weeks, so as
the graph scrolls each week the daily rebuild re-places it and it appears to
stay still. History never grows past the current window.

Config (all optional except name + email) comes from the environment:

  ART_NAME       commit author name
  ART_EMAIL      commit author email -- MUST be verified on the GitHub account
  ART_TEXT       message to render        (default "HIRE TOM")
  ART_INTENSITY  commits per lit day      (default 100)
  ART_END_GAP    blank weeks at the live edge; unset = auto-center
  ART_SIGN       "1" to GPG-sign every commit (local runs that have the key)
  ART_KEYID      signing key id, when ART_SIGN=1
"""

import datetime as dt
import os
import pathlib
import subprocess
import sys
import time

GRAPH_WEEKS = 53                               # visible columns on the graph

TEXT        = os.environ.get("ART_TEXT", "HIRE TOM")
INTENSITY   = int(os.environ.get("ART_INTENSITY", "100"))
AUTHOR_NAME = os.environ["ART_NAME"]
AUTHOR_MAIL = os.environ["ART_EMAIL"]
KEEP        = ["paint.py", ".github", "README.md", "LICENSE"]
INFRA_DATE  = "2019-01-01T12:00:00+00:00"      # explicit UTC -> identical SHAs everywhere
SIGN        = os.environ.get("ART_SIGN") == "1"
KEYID       = os.environ.get("ART_KEYID", "")

# ---------------------------------------------------------------------------
# 5-wide x 7-tall pixel font. One table -- add or retune glyphs here to change
# how ART_TEXT is drawn.
# ---------------------------------------------------------------------------
_GLYPHS = {
    "A": "01110 10001 10001 11111 10001 10001 10001",
    "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01111 10000 10000 10000 10000 10000 01111",
    "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111",
    "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01111 10000 10000 10000 10011 10001 01111",
    "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "11111 00100 00100 00100 00100 00100 11111",
    "J": "00001 00001 00001 00001 00001 10001 01110",
    "K": "10001 10010 10100 11000 10100 10010 10001",
    "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10001 10001 10001 10001",
    "N": "10001 11001 11001 10101 10011 10011 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110",
    "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101",
    "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110",
    "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110",
    "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 10101 01010",
    "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100",
    "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10011 10011 10101 11001 11001 01110",
    "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111",
    "3": "11111 00010 00100 00010 00001 10001 01110",
    "4": "00010 00110 01010 10010 11111 00010 00010",
    "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110",
    "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110",
    "9": "01110 10001 10001 01111 00001 00010 01100",
    "!": "00100 00100 00100 00100 00100 00000 00100",
    "?": "01110 10001 00001 00010 00100 00000 00100",
    ".": "00000 00000 00000 00000 00000 00000 00100",
    "-": "00000 00000 00000 11111 00000 00000 00000",
    "'": "00100 00100 00000 00000 00000 00000 00000",
}
FONT = {ch: [row.replace("0", " ").replace("1", "#") for row in spec.split()]
        for ch, spec in _GLYPHS.items()}
FONT[" "] = ["   "] * 7


def bitmap(text):
    rows = [""] * 7
    for ch in text:
        g = FONT.get(ch.upper())
        if g is None:
            raise SystemExit(f"paint.py: no glyph for {ch!r} -- add it to _GLYPHS "
                             f"or change ART_TEXT")
        w = max(len(line) for line in g)
        for r in range(7):
            rows[r] += g[r].ljust(w) + " "     # 1-col gap after each glyph
    return [r[:-1] for r in rows]              # drop the trailing gap


def run(args, env=None):
    subprocess.run(args, check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def out(args, env=None):
    return subprocess.run(args, check=True, env=env, text=True,
                          capture_output=True).stdout.strip()


def push(head, force, attempts=5):
    # GitHub only credits a push's commits reliably when it's a small,
    # incremental update. A single force-push introducing the whole painted
    # history at once (tens of thousands of commits) gets silently
    # under-counted -- only a handful of the newest days end up credited, no
    # matter how long you wait. So each lit day is pushed to `main`
    # separately, right after it's built: the first push of a run replaces
    # whatever history was there before (force), every push after that is a
    # plain fast-forward extending the one before it -- exactly the shape of
    # push GitHub has always credited correctly for this repo.
    #
    # ~110 pushes in one run over a flaky or rate-limited connection means
    # some single push failing isn't rare -- and unlike the old one-push
    # design, failing here mid-run leaves `main` without the tooling commit,
    # i.e. the repo briefly has no paint.py/README checked out. Retry with
    # backoff instead of dying on the first blip and leaving it there.
    run(["git", "update-ref", "refs/heads/_fresh", head])
    args = ["git", "push"]
    if force:
        args.append("--force")
    args += ["origin", "_fresh:refs/heads/main"]
    for attempt in range(1, attempts + 1):
        try:
            run(args)
            return
        except subprocess.CalledProcessError:
            if attempt == attempts:
                raise
            time.sleep(2 ** attempt)   # 2s, 4s, 8s, 16s


def main():
    rows  = bitmap(TEXT)
    width = len(rows[0])

    env_gap  = os.environ.get("ART_END_GAP")
    end_gap  = int(env_gap) if env_gap else max(1, round((GRAPH_WEEKS - width) / 2))
    left_gap = GRAPH_WEEKS - end_gap - width
    if end_gap < 1 or left_gap < 1:
        print(f"paint.py: WARNING text is {width} cols wide -> left={left_gap} "
              f"right={end_gap}; it may clip. Shorten ART_TEXT or set ART_END_GAP.",
              file=sys.stderr)

    today          = dt.date.today()
    days_since_sun  = (today.weekday() + 1) % 7          # Sunday -> 0
    this_sunday     = today - dt.timedelta(days=days_since_sun)
    art_start       = this_sunday - dt.timedelta(weeks=end_gap + width - 1)

    # fresh orphan branch; snapshot the repo's own files into a tree for the
    # single "tooling" commit that will sit ON TOP of the painted history.
    run(["git", "checkout", "-q", "--orphan", "_fresh"])
    run(["git", "read-tree", "--empty"])
    run(["git", "add", "--", *[k for k in KEEP if pathlib.Path(k).exists()]])
    files_tree = out(["git", "write-tree"])
    empty_tree = subprocess.run(["git", "mktree"], input="", text=True,
                                capture_output=True, check=True).stdout.strip()

    run(["git", "config", "commit.gpgsign", "true" if SIGN else "false"])
    sign_arg = [f"-S{KEYID}"] if SIGN else []

    base_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": AUTHOR_NAME,   "GIT_COMMITTER_NAME": AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": AUTHOR_MAIL,  "GIT_COMMITTER_EMAIL": AUTHOR_MAIL,
    }

    # --- painted history: empty-tree commits via git commit-tree, one
    #     calendar day at a time, oldest first (the (c, r) loop order is
    #     already chronological). Deterministic within a given week, so a
    #     re-run reproduces identical SHAs and every push below becomes a
    #     no-op. Pushed to `main` after each day -- see push() for why this
    #     can't be one push at the end.
    #
    #     Each push's tip is a tooling commit (files_tree: paint.py / the
    #     workflow / README / LICENSE) merging that day's raw painted chain
    #     onto the *previous* pushed tip -- two parents, not one. That keeps
    #     three things true at once: (1) `main` always has real files
    #     checked out, even if the run dies mid-push, so a failure can never
    #     again strip the workflow file off the branch and silently kill the
    #     cron (which is exactly what happened -- twice); (2) every pushed
    #     tip is a genuine descendant of the last one (fast-forward, via the
    #     second parent), even though tooling commits can't chain directly
    #     off each other the way the painted commits do; (3) the raw painted
    #     chain's own SHAs never depend on files_tree, so editing paint.py
    #     doesn't force a repaint of already-credited history the way a
    #     single commit "on top" at the very end would if that final push
    #     were the only place files_tree showed up. -------------------------
    infra_env = {**base_env,
                 "GIT_AUTHOR_DATE": INFRA_DATE, "GIT_COMMITTER_DATE": INFRA_DATE}

    head   = None   # tip of the raw painted (empty-tree) chain
    tip    = None   # tip of what's actually pushed to `main`
    parent = []
    total  = 0
    days   = 0
    first_push = True
    for c in range(width):
        for r in range(7):
            if rows[r][c] == " ":
                continue
            day = art_start + dt.timedelta(weeks=c, days=r)
            if day >= today:                 # can't paint today or the future
                continue
            stamp = f"{day.isoformat()}T12:00:00+00:00"   # explicit UTC (see INFRA_DATE)
            env = {**base_env, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
            for _ in range(INTENSITY):
                head = out(["git", "commit-tree", *sign_arg, empty_tree,
                            *parent, "-m", str(day)], env=env)
                parent = ["-p", head]
                total += 1
            days += 1

            tip_parents = ["-p", head] if tip is None else ["-p", head, "-p", tip]
            tip = out(["git", "commit-tree", *sign_arg, files_tree, *tip_parents,
                       "-m", "chore: contribution-art tooling"], env=infra_env)
            push(tip, force=first_push)
            first_push = False

    run(["git", "reset", "-q", "--hard", tip])
    run(["git", "branch", "-qM", "_fresh", "main"])
    print(f"painted {TEXT!r}: {width} cols, {INTENSITY}/day, {total} commits over "
          f"{days} days, {days} pushes, margins L{left_gap}/R{end_gap}, "
          f"{art_start} .. {art_start + dt.timedelta(weeks=width - 1)}")


if __name__ == "__main__":
    sys.exit(main())
