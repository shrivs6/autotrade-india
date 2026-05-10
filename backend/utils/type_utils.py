"""
Converts numpy types to native Python types for DB/JSON compatibility.
numpy.float64, numpy.int64 etc. are not JSON serializable by default.
"""
import numpy as np


def to_python(obj):
    """Recursively convert numpy scalars to native Python types."""
    if isinstance(obj, dict):
        return {k: to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_python(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj
