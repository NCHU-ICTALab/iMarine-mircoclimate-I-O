# Port-local Postprocess Validation v2.9

## KHWD Aggregation

`src/data/port_local_wind_aggregation.py` produces:

```text
khwd_wind_speed_mean
khwd_wind_speed_max
khwd_wind_speed_min
khwd_wind_speed_std
khwd_wind_gust_mean
khwd_wind_gust_max
khwd_wind_gust_min
khwd_wind_gust_std
khwd_station_count
khwd_valid_wind_station_count
khwd_valid_gust_station_count
khwd_latest_observation_time
```

## Wind/Gust Postprocess

H1/H2 are checked against KHWD max wind/gust values:

- wind speed warning/high_risk/stop thresholds
- gust warning/high_risk/stop thresholds

If KHWD values do not exceed thresholds, the report still records `applied=false` and keeps base operation levels.

## Rain Probability Preservation

v2.9 must keep rain probability independent from wind/gust postprocess. Each anchor keeps:

- `raw_model_probability`
- `nearby_adjusted_probability`
- `port_local_adjusted_probability`
- `cwa_adjusted_probability`
- `final_probability`
- `level`
- `source_detail`
