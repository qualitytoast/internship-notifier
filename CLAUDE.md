# InternWatch

Watches company careers sites and emails new internships. See README.md for how it works.

## After every change

Use the `commit-and-push` skill: commit with a short message saying what you did, then push.

## Changes that could make the filters stricter

The filters must never quietly stop sending a kind of role they used to send. If a change risks a single role that
was accepted before being rejected afterwards, stop before making or committing it. That includes:

- adding words to an exclude list in `config/filters.yaml`
- removing or narrowing role, field or term keywords
- tightening locations, terms or years
- changing how keywords match (`kw_regex`)
- changing the order or logic in `src/internwatch/filters.py`
- changing a checker so that it reads fewer jobs

Then give me:

1. A short TLDR of the new behavior.
2. A question asking whether that behavior is OK.
3. An example comparing old and new, such as `"Policy Engineering Intern": old: included (unsure) → new:
   rejected (excluded field 'Policy')`. Where you can, run the old and new filters over the stored postings
   in `data/internwatch.db` and report how many roles would stop matching, with a few real titles.

Wait for my answer before applying it. Changes that only let more roles through don't need this.
