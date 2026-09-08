import numpy as np
import pandas as pd
import pyarrow.parquet as pq

def read_column(path, name, dtype=None):
    table = pq.read_table(path, columns=[name])
    arr = table.column(0).combine_chunks()

    if name == "trade_date":
        if str(arr.type).startswith(("int", "uint")):
            return arr.to_numpy(zero_copy_only=False).astype(np.int64, copy=False)
        vals = arr.to_pylist()
        dt = pd.to_datetime(vals, errors="raise")
        if getattr(dt, "tz", None) is not None:
            dt = dt.tz_convert("Asia/Shanghai").tz_localize(None)
        dt = pd.DatetimeIndex(dt).normalize()
        return (dt.asi8 // 1000).astype(np.int64)

    if name in ("ts_code", "currency", "interval", "adjusted"):
        return np.asarray(arr.to_pylist())

    out = arr.to_numpy(zero_copy_only=False)
    if dtype is not None:
        out = out.astype(dtype, copy=False)
    return out
