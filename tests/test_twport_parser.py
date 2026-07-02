from datetime import datetime

from app.collectors.twport import normalize_row, parse_gridview1, parse_key_value, parse_tw_time
from app.models import TAIPEI


HTML_FIXTURE = """
<html><body>
<table id="GridView1">
  <tr>
    <th>ID</th><th>PortCode</th><th>DataType</th><th>DeviceType</th><th>StationName</th>
    <th>LocationMemo</th><th>Longitude</th><th>Latitude</th><th>Elevation</th>
    <th>TableName</th><th>OriginalStationID9</th>
    <th>LastData_DT</th><th>LastData_Str</th>
    <th>Y112_LastData_DT</th><th>Y112_LastData_Str</th>
    <th>Y113_Wind15minData_DT</th><th>Y113_Wind15minData_Str</th>
  </tr>
  <tr>
    <td>1</td><td>KH1</td><td>WIND</td><td>WIND</td><td>高雄港</td>
    <td>一號碼頭</td><td>120.1</td><td>22.6</td><td>5</td>
    <td>WIND_TABLE</td><td>KH-WIND-001</td>
    <td>2026/6/30 下午 08:35:00</td><td>WS_AVG=1.622,WD_AVG=335,WS_MAX=2.29,WD_MAX=323</td>
    <td>2026/6/30 下午 08:30:00</td><td>[WS_AVG]=2.261429,[WD_AVG]=179.9286,[NUM]=14,[WS_MAX]=3.96,[WD_MAX]=17,[MAX_T]=2026/6/30 下午 08:23:58</td>
    <td>2026/6/30 下午 08:15:00</td><td>WS_AVG=2,WD_AVG=180,WS_MAX=4,WD_MAX=20</td>
  </tr>
  <tr>
    <td>2</td><td>KH1</td><td>TIDE</td><td>TIDE</td><td>旗津</td>
    <td>旗津</td><td>120.2</td><td>22.7</td><td>0</td>
    <td>TIDE_TABLE</td><td></td>
    <td>2026/6/30 20:35:00</td><td>TideValue=0.919,TWVD_Value=0.371,CDL_Value=0.921</td>
    <td></td><td></td><td></td><td></td>
  </tr>
  <tr>
    <td>3</td><td>KH2</td><td>VISIBILITY</td><td>VISIBILITY</td><td>中島</td>
    <td>中島</td><td>120.3</td><td>22.8</td><td>1</td>
    <td>VIS_TABLE</td><td>VIS-001</td>
    <td>2026/6/30 上午 08:35:00</td><td>Visibility_Value=32000</td>
    <td></td><td></td><td></td><td></td>
  </tr>
</table>
</body></html>
"""


def test_key_value_parser_supports_plain_and_bracketed_values():
    assert parse_key_value("WS_AVG=1.622,WD_AVG=335") == {"WS_AVG": 1.622, "WD_AVG": 335.0}

    parsed = parse_key_value(
        "[WS_AVG]=2.261429,[WD_AVG]=179.9286,[MAX_T]=2026/6/30 下午 08:23:58"
    )

    assert parsed["WS_AVG"] == 2.261429
    assert parsed["WD_AVG"] == 179.9286
    assert parsed["MAX_T"] == "2026/6/30 下午 08:23:58"


def test_parse_tw_time_supports_chinese_meridiem_and_24_hour():
    assert parse_tw_time("2026/6/30 下午 08:35:00") == datetime(2026, 6, 30, 20, 35, tzinfo=TAIPEI)
    assert parse_tw_time("2026/6/30 上午 08:35:00") == datetime(2026, 6, 30, 8, 35, tzinfo=TAIPEI)
    assert parse_tw_time("2026/6/30 20:35:00") == datetime(2026, 6, 30, 20, 35, tzinfo=TAIPEI)


def test_gridview_and_wind_row_normalization():
    row = parse_gridview1(HTML_FIXTURE)[0]
    obs = normalize_row(row, wind_mode=10, fetched_at=datetime(2026, 6, 30, 20, 36, tzinfo=TAIPEI))

    assert obs.station_id == "KH-WIND-001"
    assert obs.station_name == "高雄港"
    assert obs.location == "一號碼頭"
    assert obs.wind_speed == 2.261429
    assert obs.wind_gust == 3.96
    assert obs.wind_direction == 179.9286
    assert obs.wind_gust_direction == 17.0
    assert obs.stale is False


def test_tide_row_normalization():
    row = parse_gridview1(HTML_FIXTURE)[1]
    obs = normalize_row(row, fetched_at=datetime(2026, 6, 30, 20, 36, tzinfo=TAIPEI))

    assert obs.station_id == "TIDE_TABLE"
    assert obs.tide_level == 0.919
    assert obs.raw_data["TWVD_Value"] == 0.371


def test_visibility_row_normalization():
    row = parse_gridview1(HTML_FIXTURE)[2]
    obs = normalize_row(row, fetched_at=datetime(2026, 6, 30, 8, 36, tzinfo=TAIPEI))

    assert obs.visibility == 32000.0
    assert obs.port_code == "KH2"


def test_stale_detection():
    row = parse_gridview1(HTML_FIXTURE)[2]
    obs = normalize_row(row, fetched_at=datetime(2026, 6, 30, 9, 10, tzinfo=TAIPEI))

    assert obs.stale is True
