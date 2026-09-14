from datetime import datetime, timedelta, timezone


def expected_session(now=None):
    local = (now or datetime.now(timezone.utc)).astimezone(
        timezone(timedelta(hours=8))
    )
    if local.weekday() >= 5 or local.hour < 15:
        raise RuntimeError("FAIL CLOSED: run on a weekday after the China market close")
    # A holiday or delayed dump must fail closed, not reuse a previous session.
    return local.date().isoformat()


def require_session(actual, expected):
    if actual != expected:
        raise RuntimeError(f"FAIL CLOSED: required session {expected}, received {actual}")


def require_account_continuity(state, dates):
    last = state.get("last_processed_date")
    code = state.get("last_processed_date_code")
    if not isinstance(code, int) or isinstance(code, bool):
        raise RuntimeError("FAIL CLOSED: account has no valid saved date index")
    if code < 0 or code >= len(dates) or dates[code] != last:
        raise RuntimeError("FAIL CLOSED: saved account date/index differs from current data")
    if len(dates) - 1 - code > 1:
        raise RuntimeError("FAIL CLOSED: account gap requires a separately reviewed recovery; no automatic backfill")
