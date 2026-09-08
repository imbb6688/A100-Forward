import numpy as np
import pyarrow.parquet as pq

def read_column(path, name, dtype=None):
    """
    Robust column reader for multi-row-group Parquet files.
    Uses pyarrow directly so all row groups are read.
    """
    table = pq.read_table(path, columns=[name])
    arr = table.column(0).combine_chunks()

    if name in ("ts_code", "trade_date", "currency", "interval", "adjusted"):
        out = arr.to_pylist()
        if name == "trade_date":
            return np.asarray(out, dtype="U10")
        return np.asarray(out)

    out = arr.to_numpy(zero_copy_only=False)
    if dtype is not None:
        out = out.astype(dtype, copy=False)
    return out
