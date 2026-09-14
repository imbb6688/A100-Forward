# A100 recovery candidate, 2026-09-14

Status: DRAFT. Do not resume account processing until recovery is reviewed.

Baseline: `6484ffd5d6a2314158372f2291eb500270f022d7`.
Verified failed run: https://github.com/imbb6688/A100-Forward/actions/runs/34600743316

## Confirmed defects and changes

- The downloader only defined `fetch` and did not invoke it. The download step exited successfully without creating any files. Restore the normalization contract from commit `4f18adbc4739c8fff3812a272d70141a69b1c5ea`, with an explicit entrypoint, bounded retries, full Parquet decoding before accepting the object, and redacted transport errors.
- Retries start each object from zero. This deliberately avoids splicing different daily dump versions through renewed signed URLs. Interrupted large downloads may take longer.
- Preflight now detects a truncated downloader. The workflow checks the expected output files before feature processing.
- Publication/account validation previously accepted mutually consistent stale dates. Require the current China weekday after 15:00; a holiday or delayed data results in failure, not reuse of yesterday's data. This is a conservative stop rule, not a complete exchange calendar.
- Missing account files previously initialized a new account; missing sessions were automatically replayed. Stop on missing files, a changed date index, or a gap of more than one available session. No state files are changed in this patch.
- The account selected a cluster using `clusters[raw]`, although cluster is a date-by-symbol matrix. Select `clusters[t, sid]`. A synthetic execution of the account script verifies that a valid latest candidate produces a pending order with the correct cluster and no immediate cash movement.
- Restrict the account/publishing workflow to main, so manually selecting a review branch cannot push that branch's state/code to main.

## Validation

16 local tests passed using Python 3.13 and the available numpy/pandas. Transport tests isolate HTTP and Parquet with doubles; they are not real downloads or end-to-end Parquet tests. The account test executes the actual script against small generated NPZ inputs and an isolated synthetic account. Syntax checks and preflight passed.

Local installation of additional dependencies failed due to temporary-directory permissions. A separate read-only PR workflow installs the repository's dependencies on Python 3.11 and checks imports, YAML, and regression tests. Its result must be checked separately. No real HiThink download, full-market feature rebuild, or Pages deployment has been verified in this recovery session.

## Required before resuming

1. Preserve the authoritative 2026-09-09 account and record the interruption. Decide on a separately labeled replay or a new forward observation segment; never silently count reconstructed days as contemporaneous forward signals.
2. Run a download/feature-only validation with the existing GitHub secret and inspect full-market dates, coverage, memory consumption, and output schemas before touching the authoritative account.
3. Resolve the following inherited model/account issues in separately reviewed work; none is silently retuned here:
   - V6 training labels use a 1.8R target while the account uses 1.5R. This may be an intended training target, but needs the original frozen specification.
   - Adjustment events are downloaded but unused by the feature and account calculations; shifted raw close is used as previous close. Corporate actions can distort returns, stop levels and account equity.
   - Account exits inspect the whole daily bar before processing pending next-open entries. Intraday sale proceeds can therefore become available to earlier opening purchases, creating optimistic fills.
   - Stored symbol indices and cluster identities need stability checks across universe changes and cluster rebalances.
   - V6 labels near the end of the available history can use shortened horizons; training-year boundaries need outcome-date auditing.
   - Dependency ranges are broad, and a fixed seed alone does not guarantee identical models across dependency upgrades.

The repository does not currently contain the previously discussed Alpha100 3.2 module. Keep Daily Stock Analysis as a later reporting integration until the frozen forward chain is validated.
