import os
import json
import time
from pathlib import Path

import requests
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


BASE = "https://fuyao.aicubes.cn"

ENDPOINTS = {
    "daily": "/api/dump/market-dumps/daily-k/download-url",
    "adj": "/api/dump/market-dumps/adjustment-factors/download-url",
}

OUT = Path("/mnt/data")
OUT.mkdir(parents=True, exist_ok=True)

KEY = os.environ.get("HITHINK_FINANCE_API_KEY")

if not KEY:
    raise SystemExit(
        "HITHINK_FINANCE_API_KEY secret is missing"
    )


MAX_DOWNLOAD_ATTEMPTS = 5
CHUNK_SIZE = 1024 * 1024
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 600


def presigned(kind):

    r = requests.get(
        BASE + ENDPOINTS[kind],
        headers={
            "X-api-key": KEY
        },
        timeout=45,
    )

    if r.status_code != 200:
        raise RuntimeError(
            f"{kind}: HTTP {r.status_code}: "
            f"{r.text[:500]}"
        )

    obj = r.json()

    code = obj.get("code")
    msg = obj.get("message", "")
    req = obj.get("request_id", "")

    if code not in (
        0,
        "0",
        None,
    ):
        raise RuntimeError(
            f"{kind}: HiThink code={code}, "
            f"message={msg!r}, "
            f"request_id={req!r}"
        )

    data = obj.get("data") or {}

    url = (
        data.get("presigned_url")
        or data.get("download_url")
    )

    if not url:
        raise RuntimeError(
            f"{kind}: no data.presigned_url; "
            f"code={code}, "
            f"message={msg!r}, "
            f"request_id={req!r}, "
            f"data_keys={list(data)[:20]}"
        )

    return url


def download_once(
    kind,
    url,
    tmp,
):

    existing = (
        tmp.stat().st_size
        if tmp.exists()
        else 0
    )

    headers = {}
    mode = "wb"

    if existing > 0:

        headers["Range"] = (
            f"bytes={existing}-"
        )

        mode = "ab"


    with requests.get(
        url,
        stream=True,
        headers=headers,
        timeout=(
            CONNECT_TIMEOUT,
            READ_TIMEOUT,
        ),
    ) as r:

        if r.status_code == 403:
            raise RuntimeError(
                f"{kind}: "
                "presigned URL HTTP 403"
            )

        if existing > 0:

            if r.status_code == 206:

                content_range = (
                    r.headers.get(
                        "Content-Range",
                        "",
                    )
                )

                expected_prefix = (
                    f"bytes {existing}-"
                )

                if not content_range.startswith(
                    expected_prefix
                ):
                    raise RuntimeError(
                        f"{kind}: unexpected "
                        f"Content-Range="
                        f"{content_range!r}"
                    )

            elif r.status_code == 200:

                # Server does not support
                # resume for this request.
                # Restart safely from zero.

                existing = 0
                mode = "wb"

            elif r.status_code == 416:

                # Requested range already
                # beyond/end of remote file.
                # Later parquet validation
                # will verify the file.

                return

            else:

                r.raise_for_status()

        else:

            r.raise_for_status()


        expected_additional = (
            r.headers.get(
                "Content-Length"
            )
        )

        if (
            expected_additional
            and
            expected_additional.isdigit()
        ):

            expected_additional = int(
                expected_additional
            )

        else:

            expected_additional = None


        before = (
            tmp.stat().st_size
            if tmp.exists()
            else 0
        )

        if mode == "wb":
            before = 0


        with tmp.open(mode) as f:

            for chunk in r.iter_content(
                chunk_size=CHUNK_SIZE
            ):

                if chunk:
                    f.write(chunk)


        after = tmp.stat().st_size


        if (
            expected_additional
            is not None
        ):

            expected_total = (
                before
                +
                expected_additional
            )

            if after != expected_total:

                raise RuntimeError(
                    f"{kind}: incomplete "
                    f"download; "
                    f"got={after} bytes, "
                    f"expected="
                    f"{expected_total} bytes"
                )


def fetch(
    kind,
    dest,
):

    tmp = dest.with_suffix(
        dest.suffix + ".part"
    )

    last_error = None


    for attempt in range(
        1,
        MAX_DOWNLOAD_ATTEMPTS + 1,
    ):

        try:

            # Always request a fresh
            # presigned URL before retrying.
            # This avoids expired signed URLs.

            url = presigned(kind)

            download_once(
                kind,
                url,
                tmp,
            )


            if (
                not tmp.exists()
                or
                tmp.stat().st_size < 1024
            ):

                raise RuntimeError(
                    f"{kind}: "
                    "implausibly small file"
                )


            tmp.replace(dest)

            return (
                dest.stat().st_size
            )


        except (
            requests.exceptions.
            ChunkedEncodingError,

            requests.exceptions.
            ConnectionError,

            requests.exceptions.
            ReadTimeout,

            requests.exceptions.
            ConnectTimeout,

            RuntimeError,

        ) as e:

            last_error = e


            if (
                attempt
                >= MAX_DOWNLOAD_ATTEMPTS
            ):

                break


            wait_seconds = min(
                5
                *
                (
                    2
                    **
                    (
                        attempt - 1
                    )
                ),
                60,
            )


            current = (
                tmp.stat().st_size
                if tmp.exists()
                else 0
            )


            print(
                f"{kind}: download "
                f"attempt {attempt} "
                f"failed after "
                f"{current} bytes: "
                f"{e}",
                flush=True,
            )


            print(
                f"{kind}: retrying in "
                f"{wait_seconds}s...",
                flush=True,
            )


            time.sleep(
                wait_seconds
            )


    raise RuntimeError(
        f"{kind}: download failed "
        f"after "
        f"{MAX_DOWNLOAD_ATTEMPTS} "
        f"attempts: "
        f"{last_error}"
    )


raw = (
    OUT
    /
    "hithink_daily_raw.parquet"
)

daily = (
    OUT
    /
    "A100_2020_2026_raw.parquet"
)

adj = (
    OUT
    /
    "A100_adjustment_factors.parquet"
)


print(
    "Downloading HiThink daily dump...",
    flush=True,
)

rb = fetch(
    "daily",
    raw,
)


print(
    "Downloading HiThink "
    "adjustment dump...",
    flush=True,
)

ab = fetch(
    "adj",
    adj,
)


#
# Validate raw parquet
#

pf = pq.ParquetFile(
    raw
)


required_columns = {
    "thscode",
    "date_ms",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    "turnover",
}


missing_columns = (
    required_columns
    -
    set(
        pf.schema.names
    )
)


if missing_columns:

    raise RuntimeError(
        "daily dump missing "
        f"columns: "
        f"{sorted(missing_columns)}"
    )


if (
    pf.metadata.num_rows
    <
    7_000_000
):

    raise RuntimeError(
        "daily dump too small: "
        f"{pf.metadata.num_rows}"
    )


#
# Load raw market data
#

df = (
    pq.read_table(
        raw
    )
    .to_pandas()
)


df = df.rename(
    columns={
        "thscode":
            "ts_code",

        "open_price":
            "open",

        "high_price":
            "high",

        "low_price":
            "low",

        "close_price":
            "close",

        "turnover":
            "amount",
    }
)


local = (
    pd.to_datetime(
        df["date_ms"],
        unit="ms",
        utc=True,
    )
    .dt
    .tz_convert(
        "Asia/Shanghai"
    )
    .dt
    .tz_localize(
        None
    )
    .dt
    .normalize()
)


df["trade_date"] = (
    local.astype(
        "int64"
    )
    //
    1000
).astype(
    "int64"
)


cut = np.int64(
    pd.Timestamp(
        "2020-01-01"
    ).value
    //
    1000
)


df = (
    df[
        df["trade_date"]
        >=
        cut
    ]
    .copy()
)


#
# Sort and deduplicate
#

df = (
    df.sort_values(
        [
            "ts_code",
            "trade_date",
        ],
        kind="mergesort",
    )
    .drop_duplicates(
        [
            "ts_code",
            "trade_date",
        ],
        keep="last",
    )
    .reset_index(
        drop=True
    )
)


df["pre_close"] = (
    df.groupby(
        "ts_code",
        sort=False,
    )["close"]
    .shift(1)
)


#
# OHLC consistency check
#

bad = (

    df["high"]

    <

    df[
        [
            "open",
            "close",
            "low",
        ]
    ].max(
        axis=1
    )

) | (

    df["low"]

    >

    df[
        [
            "open",
            "close",
            "high",
        ]
    ].min(
        axis=1
    )

)


if bool(
    bad
    .fillna(False)
    .any()
):

    raise RuntimeError(
        "bad OHLC rows="
        f"{int(bad.sum())}"
    )


#
# Preserve Frozen V7
# expected column contract
#

keep = [

    c

    for c in [

        "ts_code",
        "currency",
        "interval",
        "adjusted",
        "date_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "trade_date",
        "pre_close",

    ]

    if c in df.columns
]


df = df[
    keep
]


pq.write_table(

    pa.Table.from_pandas(
        df,
        preserve_index=False,
    ),

    daily,

    compression="snappy",

    row_group_size=
    1_000_000,

)


#
# Latest-session validation
#

latest_us = int(
    df[
        "trade_date"
    ].max()
)


latest = (
    pd.to_datetime(
        latest_us,
        unit="us",
    )
    .strftime(
        "%Y-%m-%d"
    )
)


counts = (
    df.groupby(
        "trade_date",
        sort=True,
    )
    .size()
)


nlatest = int(
    counts.loc[
        latest_us
    ]
)


prior = (
    counts[
        counts.index
        <
        latest_us
    ]
    .tail(20)
)


recent_median = (

    float(
        prior.median()
    )

    if len(prior)

    else

    float(
        nlatest
    )
)


completeness_ratio = (

    float(
        nlatest
        /
        recent_median
    )

    if recent_median > 0

    else

    0.0
)


absolute_floor_ok = bool(
    nlatest
    >=
    4500
)


relative_completeness_ok = bool(
    completeness_ratio
    >=
    0.97
)


full_market = bool(

    absolute_floor_ok

    and

    relative_completeness_ok

)


manifest = {

    "schema_version":
        "A100-HITHINK-NORMALIZED-v2",

    "source":
        "HiThink Financial-API "
        "full-market daily-k + "
        "adjustment events",

    "latest_trade_date":
        latest,

    "latest_trade_date_us":
        latest_us,

    "latest_rows":
        nlatest,

    "recent_20_session_median_rows":
        recent_median,

    "completeness_ratio":
        completeness_ratio,

    "absolute_floor_rows":
        4500,

    "minimum_completeness_ratio":
        0.97,

    "absolute_floor_ok":
        absolute_floor_ok,

    "relative_completeness_ok":
        relative_completeness_ok,

    "full_market":
        full_market,

    "complete":
        full_market,

    "data_valid":
        full_market,

    "rows":
        int(
            len(df)
        ),

    "symbols":
        int(
            df[
                "ts_code"
            ].nunique()
        ),

    "raw_daily_bytes":
        int(rb),

    "normalized_daily_bytes":
        int(
            daily.stat().st_size
        ),

    "adjustment_bytes":
        int(ab),

    "price_basis":
        "unadjusted "
        "(matches frozen V7 "
        "research contract)",
}


(
    OUT
    /
    "hithink_manifest.json"
).write_text(

    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ),

    encoding=
    "utf-8",
)


print(

    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ),

    flush=True,
)


if not full_market:

    raise SystemExit(

        "FAIL CLOSED: incomplete "
        "full-market session: "

        f"latest_rows="
        f"{nlatest}, "

        f"recent_median="
        f"{recent_median:.1f}, "

        f"completeness_ratio="
        f"{completeness_ratio:.4f}"

    )
