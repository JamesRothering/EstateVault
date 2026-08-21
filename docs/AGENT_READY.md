# Standing orders for a Cursor cloud agent started from a `ready` GitHub issue

You are implementing **one** GitHub issue in JamesRothering/EstateVault. Open a pull request. **Do not merge. Do not force-push `main`.**

## Product

Firefly III is the only financial ledger (official Docker image). Estate is a thin Python dashboard that reads the Firefly API. Never store transactions in Estate. Never fork or modify Firefly source.

## Process

1. Pick only the issue in this prompt. If `docs/BACKLOG.md` already lists it as implemented on `main`, add any missing tests and a small PR that closes the issue — do not reimplement.
2. Tests first (red), then code (green). `python3 -m unittest discover -s tests -v` must stay green.
3. One story, one branch, one PR. Commit as the GitHub actor this environment provides.
4. PR body: summary, test plan, `Closes #<issue>`. Leave the PR open for James.
5. Do not add GitHub secrets, tokens, or `.env` to git.

## Environments

- **Stable** is `main` at http://127.0.0.1:8080 (Firefly) and http://127.0.0.1:8090 (Estate). Do not point those ports at your branch.
- **Review** is the PR, tried at http://127.0.0.1:8190 via `scripts/review_up.sh`.
- GitHub Actions runs unit tests. That is not a running Firefly.

If you cannot finish, comment on the issue with what blocked you and still leave a draft PR if there is code.
