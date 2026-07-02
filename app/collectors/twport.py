from __future__ import annotations

import argparse
import asyncio
import html
import json
import logging
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

import httpx

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - exercised only when dependency is absent
    BeautifulSoup = None  # type: ignore[assignment]

from app.config import Settings, settings
from app.models import TAIPEI, TwPortObservation
from app.storage import ObservationStore


logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 microclimate-collector/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml",
    "Referer": "https://wwtf.twport.com.tw/",
}

EMPTY_VALUES = {"", "-", "&nbsp;", "\xa0", "-999"}


def build_endpoint(config: Settings, wind_mode: int) -> str:
    endpoint_mode = 0 if wind_mode == 10 else wind_mode
    return f"{config.twport_base_url}?{config.twport_port_id},{endpoint_mode}"


async def fetch_html(wind_mode: int = 1, config: Settings = settings) -> str:
    url = build_endpoint(config, wind_mode)
    last_error: Exception | None = None
    async with httpx.AsyncClient(
        timeout=config.request_timeout_seconds,
        headers=HEADERS,
        verify=config.twport_verify_ssl,
    ) as client:
        for attempt in range(1, 4):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
            except Exception as exc:
                last_error = exc
                logger.warning("TWPort fetch failed attempt=%s url=%s error=%s", attempt, url, exc)
                if attempt < 3:
                    await asyncio.sleep(5)
    raise RuntimeError(f"TWPort fetch failed after retries: {last_error}")


def parse_gridview1(document: str) -> list[dict[str, str]]:
    if BeautifulSoup is None:
        return parse_gridview1_with_stdlib(document)
    soup = BeautifulSoup(document, "html.parser")
    table = soup.find("table", id="GridView1")
    if table is None:
        raise ValueError("GridView1 table not found")

    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [cell.get_text(strip=True) for cell in rows[0].find_all(["th", "td"])]
    records: list[dict[str, str]] = []
    for row in rows[1:]:
        cells = [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])]
        if not cells:
            continue
        record = {headers[index]: cells[index] if index < len(cells) else "" for index in range(len(headers))}
        records.append(record)
    return records


class GridViewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_grid = False
        self.in_cell = False
        self.depth = 0
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table" and attrs_dict.get("id") == "GridView1":
            self.in_grid = True
            self.depth = 1
            return
        if not self.in_grid:
            return
        if tag == "table":
            self.depth += 1
        if tag == "tr":
            self.current_row = []
        if tag in ("td", "th"):
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if not self.in_grid:
            return
        if tag in ("td", "th") and self.in_cell:
            self.current_row.append("".join(self.current_cell).strip())
            self.in_cell = False
        elif tag == "tr" and self.current_row:
            self.rows.append(self.current_row)
        elif tag == "table":
            self.depth -= 1
            if self.depth <= 0:
                self.in_grid = False

    def handle_data(self, data: str) -> None:
        if self.in_grid and self.in_cell:
            self.current_cell.append(data)


def parse_gridview1_with_stdlib(document: str) -> list[dict[str, str]]:
    parser = GridViewParser()
    parser.feed(document)
    if not parser.rows:
        raise ValueError("GridView1 table not found")
    headers = parser.rows[0]
    records = []
    for cells in parser.rows[1:]:
        records.append({headers[index]: cells[index] if index < len(cells) else "" for index in range(len(headers))})
    return records


def parse_key_value(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    text = html.unescape(str(raw)).strip()
    if text in EMPTY_VALUES:
        return {}

    values: dict[str, Any] = {}
    for part in text.split(","):
        if "=" not in part:
            if part.strip():
                logger.warning("Skipping malformed key-value part: %s", part)
            continue
        key, value = part.split("=", 1)
        key = key.strip().strip("[]")
        if not key:
            logger.warning("Skipping key-value part with empty key: %s", part)
            continue
        values[key] = normalize_value(value)
    return values


def normalize_value(value: Any) -> Any:
    if value is None:
        return None
    text = html.unescape(str(value)).strip()
    if text in EMPTY_VALUES:
        return None
    try:
        return float(text)
    except ValueError:
        return text


def parse_tw_time(value: str | None) -> datetime | None:
    if not value or normalize_value(value) is None:
        return None
    text = html.unescape(value).strip()
    match = re.match(r"^(\d{4}/\d{1,2}/\d{1,2})\s*(上午|下午)?\s*(\d{1,2}:\d{2}:\d{2})$", text)
    if match:
        date_text, meridiem, time_text = match.groups()
        hour, minute, second = [int(part) for part in time_text.split(":")]
        if meridiem == "下午" and hour < 12:
            hour += 12
        if meridiem == "上午" and hour == 12:
            hour = 0
        year, month, day = [int(part) for part in date_text.split("/")]
        return datetime(year, month, day, hour, minute, second, tzinfo=TAIPEI)

    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=TAIPEI)
        except ValueError:
            pass
    logger.warning("Unable to parse TWPort datetime: %s", value)
    return None


def normalize_row(row: dict[str, str], wind_mode: int = 1, fetched_at: datetime | None = None) -> TwPortObservation | None:
    fetched_at = fetched_at or datetime.now(TAIPEI)
    data_type = clean_text(row.get("DataType"))
    device_type = clean_text(row.get("DeviceType")) or data_type or "UNKNOWN"
    time_key, data_key = choose_data_columns(row, device_type, wind_mode)
    obs_time = parse_tw_time(row.get(time_key)) or fetched_at
    raw_last_data_str = row.get(data_key) or ""
    raw_data = parse_key_value(raw_last_data_str)

    station_id = (
        clean_text(row.get("OriginalStationID9"))
        or clean_text(row.get("TableName"))
        or clean_text(row.get("ID"))
        or clean_text(row.get("StationName"))
        or "unknown"
    )
    observation = TwPortObservation(
        source="twport",
        port_code=clean_text(row.get("PortCode")),
        station_id=station_id,
        station_name=clean_text(row.get("StationName")) or station_id,
        location=clean_text(row.get("LocationMemo")),
        device_type=device_type,
        obs_time=obs_time,
        longitude=to_float(row.get("Longitude")),
        latitude=to_float(row.get("Latitude")),
        elevation=to_float(row.get("Elevation")),
        raw_data=raw_data,
        raw_last_data_str=raw_last_data_str,
        stale=(fetched_at - obs_time).total_seconds() > 20 * 60,
        fetched_at=fetched_at,
    )
    apply_measurements(observation, raw_data)
    return observation


def choose_data_columns(row: dict[str, str], device_type: str, wind_mode: int) -> tuple[str, str]:
    device = device_type.upper()
    candidates: list[tuple[str, str]]
    if "WIND" in device:
        if wind_mode == 15:
            candidates = [("Y113_Wind15minData_DT", "Y113_Wind15minData_Str")]
        elif wind_mode in (0, 10):
            candidates = [("Y112_LastData_DT", "Y112_LastData_Str")]
        else:
            candidates = [("LastData_DT", "LastData_Str")]
        candidates.append(("LastData_DT", "LastData_Str"))
    else:
        candidates = [
            ("LastData_DT", "LastData_Str"),
            ("Y112_LastData_DT", "Y112_LastData_Str"),
            ("Y113_Wind15minData_DT", "Y113_Wind15minData_Str"),
        ]
        candidates.sort(
            key=lambda item: parse_tw_time(row.get(item[0])) or datetime.min.replace(tzinfo=TAIPEI),
            reverse=True,
        )
    for time_key, data_key in candidates:
        if clean_text(row.get(time_key)) and parse_key_value(row.get(data_key)):
            return time_key, data_key
    return "LastData_DT", "LastData_Str"


def apply_measurements(observation: TwPortObservation, raw_data: dict[str, Any]) -> None:
    observation.wind_speed = numeric_first(raw_data, ["WS_AVG"])
    observation.wind_gust = numeric_first(raw_data, ["WS_MAX"])
    observation.wind_direction = numeric_first(raw_data, ["WD_AVG"])
    observation.wind_gust_direction = numeric_first(raw_data, ["WD_MAX"])
    observation.tide_level = numeric_first(raw_data, ["TideValue", "Tide_Value"])
    observation.visibility = numeric_first(raw_data, ["Visibility_Value"])
    observation.wave_height = numeric_first(raw_data, ["Hs"])
    observation.wave_period = numeric_first(raw_data, ["Tp"])
    observation.wave_max_height = numeric_first(raw_data, ["Hmax"])
    observation.current_speed = numeric_first(raw_data, ["Velocity", "ADCP_Velocity"])
    observation.current_direction = numeric_first(raw_data, ["Vmdir", "ADCP_Vmdir"])


def numeric_first(data: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value)).strip()
    if text in EMPTY_VALUES:
        return None
    return text


def to_float(value: Any) -> float | None:
    normalized = normalize_value(value)
    return float(normalized) if isinstance(normalized, (int, float)) else None


async def collect(wind_mode: int = 1, config: Settings = settings) -> list[TwPortObservation]:
    document = await fetch_html(wind_mode=wind_mode, config=config)
    rows = parse_gridview1(document)
    fetched_at = datetime.now(TAIPEI)
    observations = [normalize_row(row, wind_mode=wind_mode, fetched_at=fetched_at) for row in rows]
    return [item for item in observations if item is not None]


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wind-mode", type=int, choices=[1, 10, 15], default=1)
    parser.add_argument("--print", action="store_true", dest="print_output")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    observations = await collect(wind_mode=args.wind_mode)
    if args.save:
        store = ObservationStore(settings.database_path)
        store.upsert_many(observations)
    if args.print_output or not args.save:
        print(json.dumps([item.to_dict() for item in observations], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
