"""Fail-closed guards for the Forward Account recovery boundary."""


def require_authoritative_state(paths):
    missing = [path.name for path in paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(
            "FAIL CLOSED: authoritative account files missing or empty: "
            + ", ".join(sorted(missing))
        )


def require_account_continuity(state, dates):
    last_date = state.get("last_processed_date")
    last_code = state.get("last_processed_date_code")
    if not isinstance(last_code, int) or isinstance(last_code, bool):
        raise RuntimeError("FAIL CLOSED: account has no valid saved date index")
    if last_code < 0 or last_code >= len(dates):
        raise RuntimeError("FAIL CLOSED: saved account date index is outside current data")
    if dates[last_code] != last_date:
        raise RuntimeError("FAIL CLOSED: saved account date/index differs from current data")
    gap = len(dates) - 1 - last_code
    if gap > 1:
        raise RuntimeError(
            "FAIL CLOSED: account gap requires separately reviewed recovery; "
            "no automatic historical replay"
        )
