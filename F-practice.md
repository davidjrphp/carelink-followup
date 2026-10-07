# F. Delivery and engineering practice (from a software engineer's seat)

I would not set team structure, but I can change how my own work lands and push hard for a few things. I would model what I want from the team: small changes, everything reviewed, every bug gets a test.

## The two changes I would push for first

1. **Stop fixes being applied directly on the production server.** This is the biggest source of untraceable defects and the biggest patient-safety risk. Asking the two engineers to stop is not enough: they patch production because the normal path is too slow. I would pair with them to build a **hotfix lane** (branch, pull request with one reviewer, automated build and deploy) that takes under an hour.
2. **A CI pipeline every pull request must pass, with tests the team trusts.** Quarantine the tests that fail for unrelated reasons and add a regression test for every defect fixed, so coverage grows where the bugs actually are.

## Days 1–30: make changes visible and safe

- **Do:** branch protection on `main` (one approval, CI green); a short pull-request template (what changed, how tested, migration and rollback); a formatter and linter that run automatically, so standards stop being an argument; test-first for every bug I fix.
- **Leave alone:** the 300-item backlog, large technical debt, team structure.
- **Know it worked:** zero direct production changes; most pull requests reviewed within a day; CI pass rate rising.

## Days 31–60: make releases boring

- **Do:** build once and deploy the same artefact to staging and production with a scripted rollback; an expand/contract migration checklist so releases don't break older clients; API docs generated from code (OpenAPI) so they can't go stale; help the business analyst write an example-based acceptance criterion per story, which turns "requirements keep changing" into a conversation.
- **Leave alone:** rewriting legacy modules.
- **Know it worked:** release time falling from three days; fewer hotfixes; fewer defects traced to the previous fortnight.

## Days 61–90: make it sustainable

- **Do:** help tag the backlog (bug, clinic-reported, debt, feature) and write down the top ten debt items with the clinic risk each carries; mentor the juniors through review and pairing; publish lead time, change failure rate and time to restore.
- **Know it worked:** programme teams can see what is coming and why; juniors ship reviewed changes on their own.

## How I would behave meanwhile

Keep my pull requests small and test-backed; bring problems with a proposed fix; never blame the people who patched production, since they were keeping clinics running; and push for nothing that needs a delivery freeze.
