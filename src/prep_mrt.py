"""
Step B4 - MRT/LRT stations and ridership (daytime / worker demand context).

Input : raw/07_train_passenger_volumeEDA.xlsx (LTA DataMall, Aug-2026, monthly totals by hour)
        external/onemap_mrt_geocode_cache.csv (coords for stations blank in file 07)
Output: interim/dim_mrt_station.csv       one row per PT_CODE (+ avg daily volumes)
        interim/fact_mrt_hourly.csv       stn_key x day_type x hour, monthly totals + daily averages

Monthly totals are converted to *average per day* by dividing by the number of
days of that day type in the month (weekdays exclude public holidays).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
from geo import assign_points_to_features, latlon_to_svy21, name_key, read_geojson


def day_counts(month: str, holidays: list[str]) -> dict:
    days = pd.date_range(f"{month}-01", periods=pd.Period(month).days_in_month, freq="D")
    hol = pd.to_datetime(holidays)
    wk = ((days.weekday < 5) & ~days.isin(hol)).sum()
    return {"WEEKDAY": int(wk), "WEEKENDS/HOLIDAY": int(len(days) - wk)}


def main():
    d = pd.read_excel(config.RAW_FILES["mrt_volume"], sheet_name=0)
    d["MRT_STATION"] = d["MRT_STATION"].str.strip()
    n_days = day_counts(config.MRT_MONTH, config.MRT_PUBLIC_HOLIDAYS)
    print("  days in month by type:", n_days)

    f = d.rename(columns={"PT_CODE": "stn_key", "DAY_TYPE": "day_type", "TIME_PER_HOUR": "hour",
                          "TOTAL_TAP_IN_VOLUME": "tap_in_month", "TOTAL_TAP_OUT_VOLUME": "tap_out_month"})
    f["n_days"] = f["day_type"].map(n_days)
    f["tap_in_avg_day"] = f["tap_in_month"] / f["n_days"]
    f["tap_out_avg_day"] = f["tap_out_month"] / f["n_days"]
    f[["stn_key", "day_type", "hour", "tap_in_month", "tap_out_month", "n_days",
       "tap_in_avg_day", "tap_out_avg_day"]].to_csv(config.INTERIM / "fact_mrt_hourly.csv", index=False)

    st = d.drop_duplicates("PT_CODE")[["PT_CODE", "MRT_STATION", "MRT_STATION_lower", "TYPE",
                                       "LATITUDE", "LONGITUDE"]].copy()
    st.columns = ["stn_key", "station_name", "station_name_display", "rail_type", "lat", "lon"]
    st["station_key"] = st["station_name"].map(name_key)  # same location for e.g. STEVENS DT10 / TE11
    st["coord_source"] = np.where(st["lat"].notna(), "file_07", None)
    cache = config.EXTERNAL_FILES["mrt_geocode_cache"]
    if cache.exists():
        c = pd.read_csv(cache).set_index("PT_CODE")
        m = st["lat"].isna() & st["stn_key"].isin(c.index)
        st.loc[m, "lat"] = st.loc[m, "stn_key"].map(c["lat"])
        st.loc[m, "lon"] = st.loc[m, "stn_key"].map(c["lon"])
        st.loc[m, "coord_source"] = "onemap"
    if st["lat"].isna().any():
        print("  stations still without coordinates (run fetch_onemap.py mrt):",
              st.loc[st.lat.isna(), "station_name"].tolist())
    st["x_svy21"], st["y_svy21"] = latlon_to_svy21(st["lat"], st["lon"])

    wk = f[f.day_type == "WEEKDAY"]
    agg = pd.DataFrame({
        "wkday_tap_in_avg": wk.groupby("stn_key")["tap_in_avg_day"].sum(),
        "wkday_tap_out_avg": wk.groupby("stn_key")["tap_out_avg_day"].sum(),
        "wkday_am_peak_tap_out_avg": wk[wk.hour.isin(config.DAYTIME_AM_PEAK_HOURS)]
            .groupby("stn_key")["tap_out_avg_day"].sum(),
        "wkday_lunch_tap_in_avg": wk[wk.hour.isin([11, 12, 13])].groupby("stn_key")["tap_in_avg_day"].sum(),
        "wkday_lunch_tap_out_avg": wk[wk.hour.isin([11, 12, 13])].groupby("stn_key")["tap_out_avg_day"].sum(),
    }).round(1)
    st = st.merge(agg, left_on="stn_key", right_index=True, how="left")

    st["sz_key"] = None
    sz_path = config.EXTERNAL_FILES["subzone_geojson"]
    ok = st["lat"].notna()
    if sz_path.exists():
        feats = read_geojson(sz_path)
        for ft in feats:
            ft.props["sz_key"] = name_key(ft.props.get("SUBZONE_N"))
        st.loc[ok, "sz_key"], _ = assign_points_to_features(st.loc[ok, ["x_svy21", "y_svy21"]].to_numpy(), feats, "sz_key")
    st.to_csv(config.INTERIM / "dim_mrt_station.csv", index=False)
    print(f"dim_mrt_station: {len(st)} codes, {st.station_key.nunique()} physical stations")


if __name__ == "__main__":
    main()
