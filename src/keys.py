"""
Surrogate / natural key builders shared by every script, so the same entity
always gets the same key no matter which source it came from.

Key catalogue (see README "Data model"):
    pa_key      planning area   = name_key(planning area name)        e.g. 'ANG MO KIO'
    sz_key      subzone         = name_key(subzone name)              e.g. 'ANG MO KIO TOWN CENTRE'
    sz_code     subzone         = URA MP2019 SUBZONE_C code           e.g. 'AMSZ01' (when boundaries fetched)
    hc_key      hawker centre   = 'HC' + 3-digit sequence             e.g. 'HC007'
    block_id    HDB block       = '<BLK_NO>|<STREET as in HDB file>'  e.g. '1|BEACH RD'
    dp_key      demand point    = '<TYPE>-<id>'                       e.g. 'HDB-1|BEACH RD', 'CONDO-P00042', 'LANDED-G012345'
    stn_key     MRT/LRT station = PT_CODE                              e.g. 'NS24'
"""
from __future__ import annotations

import pandas as pd

from geo import name_key  # re-export

__all__ = ["name_key", "hdb_block_id"]


def hdb_block_id(blk_no: pd.Series, street: pd.Series) -> pd.Series:
    return blk_no.astype(str).str.strip().str.upper() + "|" + street.astype(str).str.strip().str.upper()
