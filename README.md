# hire-me

**Paint a message across your GitHub contribution graph — and keep it there.**

```
Sun  ····#···#·#####·####··#####·····#####··###··#···#····
Mon  ····#···#···#···#···#·#···········#···#···#·##·##····
Tue  ····#···#···#···#···#·#···········#···#···#·#·#·#····
Wed  ····#####···#···####··####········#···#···#·#···#····
Thu  ····#···#···#···#·#···#···········#···#···#·#···#····
Fri  ····#···#···#···#··#··#···········#···#···#·#···#····
Sat  ····#···#·#####·#···#·#####·······#····###··#···#····
         H    I    R    E         T    O    M
```

Every `#` is a day with a burst of back-dated commits, so GitHub draws it as a
filled square. A daily GitHub Action redraws the whole thing so it never scrolls
off the edge. No servers, no bots — just `git` and one workflow file.

---

## Use it on your own profile

1. **Click "Use this template" → "Create a new repository."** Not *fork* —
   GitHub doesn't count contributions from forks toward your graph, and forks
   start with Actions turned off. The template button gives you a clean
   standalone repo. Make it **public**.

2. **Add three repository variables.** In your new repo:
   **Settings → Secrets and variables → Actions → Variables → New repository
   variable.**

   | Variable     | Example            | Notes |
   |--------------|--------------------|-------|
   | `ART_TEXT`   | `HIRE ADA`         | Your message. `A–Z 0–9`, space, and `. - ! ? '`. About 8 characters fills the graph. |
   | `ART_NAME`   | `Ada Lovelace`     | The commit author name. |
   | `ART_EMAIL`  | `ada@example.com`  | Must be an email **verified on your GitHub account** (Settings → Emails), or the commits won't count. Your `1234+user@users.noreply.github.com` also works. |

   The template copies the code but **not** the variables, so you set these
   yourself. No files to edit.

3. **Run it.** Repo **Actions** tab → enable workflows if prompted →
   **paint-contributions** → **Run workflow.**

4. Your graph fills in within a few minutes to a day. After that the Action runs
   itself every day at 07:23 UTC and keeps the message centered as the weeks
   scroll.

To remove it: delete the repo, or disable the workflow and let it scroll off
over the next year.

---

## Change it to fit your needs

Everything is a repository variable — no code changes.

| Variable        | Default       | Effect |
|-----------------|---------------|--------|
| `ART_TEXT`      | `HIRE TOM`    | The message. Unknown characters abort with a note. |
| `ART_INTENSITY` | `100`         | Commits per lit day. GitHub shades each day relative to your busiest day across **all** repos, so if you have heavy real-commit days, raise this so the letters stay dark. |
| `ART_END_GAP`   | *auto-center* | Blank weeks to leave at the recent (right) edge; higher = further left. Only does something for a short message — a wide one has no slack to move. |

**Sizing:** each letter is 5 columns plus a 1-column gap, and the graph is only
~53 columns, so roughly 8 characters is the ceiling. A longer message triggers a
"may clip" warning and stays centered.

**New characters / different letterforms:** edit the `_GLYPHS` table in
[`paint.py`](paint.py). Each entry is seven space-separated groups of `0`/`1`
(one per row, top to bottom), five columns wide.

---

## How it works

The contribution graph is a fixed grid — 7 rows (Sun→Sat) × ~53 columns (one per
week) — and each square's shade is just *how many commits you authored that day*,
bucketed against your busiest day. Two facts make the trick possible:

- **A commit can carry any date.** `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE`
  are plain environment variables.
- **GitHub counts a commit** when its author email is verified on your account,
  it's on the default branch, and the repo isn't a fork. *When* it was pushed
  doesn't matter.

So [`paint.py`](paint.py):

1. Renders `ART_TEXT` into a 7-row bitmap with the built-in 5×7 font.
2. Finds where "now" sits on the grid (this week's Sunday is the rightmost
   column) and centers the bitmap — or offsets it by `ART_END_GAP` weeks.
3. For every lit pixel, computes its calendar date and makes `ART_INTENSITY`
   empty commits stamped with that date, via `git commit-tree` (fast enough for
   thousands in seconds).
4. Adds one commit on top holding the repo's own files, dated 2019 — outside the
   one-year window, so it's never a stray square. Because the files sit *above*
   the painted commits, editing them never rewrites the art.
5. Force-pushes the result as a fresh `main`.

**Why rebuild daily?** The graph only shows the trailing ~53 weeks and scrolls
one column left each week. Written once, the message would drift off the left
edge within a year. Instead the Action repaints from scratch every day, anchored
to the current week, so on screen it holds still. The painted commits are
deterministic within a week, so most days the rebuild produces the identical
history and the push changes nothing. A missed run fixes itself on the next one.

**Why the newest weeks stay blank:** you can't date a commit in the future, so
the script keeps the message a couple of weeks behind the live edge.

---

## License

[The Unlicense](LICENSE) — public domain, do whatever you want.

**Enjoy.** 🎨
