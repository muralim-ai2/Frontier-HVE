---
name: feature-checklist
description: Turn a request into feature_list.json for the harness loop - independently verifiable features, each with a shell check that exits 0 only when the feature works. Use before loop.py init.
---

# Feature checklist

1. Read the request (and `design.json` if it exists). Split it into 3-8 features a user would recognise ("palette generator", "contrast check", "export"), not technical layers.
2. For each feature write:
   - `name`: lowercase, digits, `-` or `_`.
   - `description`: one sentence with the observable result.
   - `verify`: a shell command run from the project root that exits 0 only when the feature works (a test file, a build plus a script that checks output). Never `echo`, `true` or `exit 0`. If the check covers several assertions, print `HARNESS_CHECKS <passed>/<total>` so the harness can rank partial progress.
   - `passes`: `false`.
3. Write the list to `feature_list.json` in the project root, then run `python <tools>/loop/loop.py init . --review <local|github>` (`<tools>` is the harness tools folder named in your agent instructions).
4. For an `executive` or `partial` user, also show the checklist as a short table (feature, what you will see when it works) before building.

After `init` the list is locked: names, descriptions and checks cannot change (anti-gaming). Get them right first.
