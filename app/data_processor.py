"""Data cleaning, transformation, and statistical analysis using Pandas and NumPy."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.exceptions import DataProcessingError

WMO_WEATHER_CODES: dict[int, str] = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    56: "Light Freezing Drizzle",
    57: "Dense Freezing Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    66: "Light Freezing Rain",
    67: "Heavy Freezing Rain",
    71: "Slight Snowfall",
    73: "Moderate Snowfall",
    75: "Heavy Snowfall",
    77: "Snow Grains",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ Slight Hail",
    99: "Thunderstorm w/ Heavy Hail",
}


@dataclass
class WeatherAnalytics:
    """Container holding cleaned daily weather data, summary statistics, and insights."""

    cleaned_df: pd.DataFrame
    stats: dict[str, Any]
    insights: list[str]
    metadata: dict[str, Any]


def map_weather_code(code: Any) -> str:
    """Translate a WMO numeric weather code into a human-readable condition."""
    if pd.isna(code):
        return "Unknown"
    try:
        numeric = int(round(float(code)))
    except (TypeError, ValueError):
        return "Unknown"
    return WMO_WEATHER_CODES.get(numeric, f"Condition ({numeric})")


def extract_daily_dataframe(payload: dict[str, Any]) -> pd.DataFrame:
    """Transform an Open-Meteo or sample weather payload into a raw Pandas DataFrame."""
    if not isinstance(payload, dict) or "daily" not in payload:
        raise DataProcessingError("Payload does not contain a 'daily' weather section.")

    daily = payload["daily"]
    if not isinstance(daily, dict) or not daily.get("time"):
        raise DataProcessingError("Daily weather payload contains no time series records.")

    row_count = len(daily["time"])

    def _get_series(key: str, default_val: Any = np.nan) -> list[Any]:
        values = daily.get(key)
        if values is None:
            return [default_val] * row_count
        if len(values) != row_count:
            raise DataProcessingError(
                f"Length mismatch for '{key}': expected {row_count}, got {len(values)}."
            )
        return list(values)

    raw_df = pd.DataFrame(
        {
            "date": _get_series("time", None),
            "temp_max": _get_series("temperature_2m_max"),
            "temp_min": _get_series("temperature_2m_min"),
            "temp_mean": _get_series("temperature_2m_mean"),
            "precipitation": _get_series("precipitation_sum", 0.0),
            "wind_speed_max": _get_series("windspeed_10m_max"),
            "weather_code": _get_series("weathercode", 0),
        }
    )
    return raw_df


def clean_weather_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Clean, deduplicate, convert types, and impute missing values on weather records.

    Returns:
        Tuple of (cleaned_df, quality_metrics).
    """
    if raw_df.empty:
        raise DataProcessingError("Cannot clean an empty weather DataFrame.")

    df = raw_df.copy()
    raw_row_count = len(df)

    # Convert date column and drop unparseable dates.
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    invalid_dates_dropped = int(df["date"].isna().sum())
    df = df.dropna(subset=["date"]).copy()

    if df.empty:
        raise DataProcessingError("All rows had invalid or missing dates after type conversion.")

    numeric_columns = ["temp_max", "temp_min", "temp_mean", "precipitation", "wind_speed_max", "weather_code"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort chronologically before deduplicating so earliest valid entry is kept cleanly.
    df = df.sort_values(by="date", ascending=True).reset_index(drop=True)

    before_dedup = len(df)
    df = df.drop_duplicates(subset=["date"], keep="first").reset_index(drop=True)
    duplicates_removed = before_dedup - len(df)

    # Count missing numeric values prior to imputation.
    missing_before = int(df[["temp_max", "temp_min", "temp_mean", "precipitation", "wind_speed_max"]].isna().sum().sum())

    # Derive temp_mean from (temp_max + temp_min) / 2 wherever available before general imputation.
    both_bounds = df["temp_max"].notna() & df["temp_min"].notna()
    missing_mean_mask = df["temp_mean"].isna() & both_bounds
    df.loc[missing_mean_mask, "temp_mean"] = (
        df.loc[missing_mean_mask, "temp_max"] + df.loc[missing_mean_mask, "temp_min"]
    ) / 2.0

    # Interpolate/fill missing temperature bounds if partial gaps exist.
    for temp_col in ("temp_max", "temp_min"):
        if df[temp_col].isna().any() and df[temp_col].notna().any():
            df[temp_col] = df[temp_col].interpolate(method="linear", limit_direction="both")
            df[temp_col] = df[temp_col].fillna(df[temp_col].mean())

    # Drop rows if temperature bounds remain completely unrecoverable.
    df = df.dropna(subset=["temp_max", "temp_min"]).copy()
    if df.empty:
        raise DataProcessingError(
            "No usable temperature records remained after missing-value handling."
        )

    # Ensure temp_max >= temp_min in case of corrupted input records.
    inverted_mask = df["temp_max"] < df["temp_min"]
    if inverted_mask.any():
        max_vals = df.loc[inverted_mask, ["temp_max", "temp_min"]].max(axis=1)
        min_vals = df.loc[inverted_mask, ["temp_max", "temp_min"]].min(axis=1)
        df.loc[inverted_mask, "temp_max"] = max_vals
        df.loc[inverted_mask, "temp_min"] = min_vals

    # Recompute any still-missing temp_mean after bounds are guaranteed present.
    still_missing_mean = df["temp_mean"].isna()
    if still_missing_mean.any():
        df.loc[still_missing_mean, "temp_mean"] = (
            df.loc[still_missing_mean, "temp_max"] + df.loc[still_missing_mean, "temp_min"]
        ) / 2.0

    # Fill precipitation (non-negative) and wind speed.
    df["precipitation"] = df["precipitation"].fillna(0.0).clip(lower=0.0)
    wind_median = df["wind_speed_max"].median()
    df["wind_speed_max"] = df["wind_speed_max"].fillna(0.0 if pd.isna(wind_median) else float(wind_median)).clip(lower=0.0)
    df["weather_code"] = df["weather_code"].fillna(0).round().astype(int)

    # Derived analytics columns.
    df["temp_range"] = (df["temp_max"] - df["temp_min"]).round(2)
    df["weather_description"] = df["weather_code"].apply(map_weather_code)

    # Round numerical columns consistently.
    for col in ("temp_max", "temp_min", "temp_mean", "precipitation", "wind_speed_max", "temp_range"):
        df[col] = df[col].round(2)

    df = df.sort_values(by="date", ascending=True).reset_index(drop=True)

    quality_metrics = {
        "raw_rows": raw_row_count,
        "cleaned_rows": len(df),
        "invalid_dates_dropped": invalid_dates_dropped,
        "duplicates_removed": duplicates_removed,
        "missing_values_imputed": missing_before,
    }
    return df, quality_metrics


def compute_weather_statistics(df: pd.DataFrame) -> dict[str, Any]:
    """Compute descriptive and trend statistics using NumPy and Pandas."""
    if df.empty:
        raise DataProcessingError("Cannot compute statistics on an empty DataFrame.")

    temp_max_arr = df["temp_max"].to_numpy(dtype=float)
    temp_min_arr = df["temp_min"].to_numpy(dtype=float)
    temp_mean_arr = df["temp_mean"].to_numpy(dtype=float)
    precip_arr = df["precipitation"].to_numpy(dtype=float)
    wind_arr = df["wind_speed_max"].to_numpy(dtype=float)
    range_arr = df["temp_range"].to_numpy(dtype=float)

    warmest_idx = int(np.argmax(temp_max_arr))
    coolest_idx = int(np.argmin(temp_min_arr))
    wettest_idx = int(np.argmax(precip_arr))

    if len(df) >= 2:
        x_days = np.arange(len(df), dtype=float)
        slope = float(np.polyfit(x_days, temp_mean_arr, 1)[0])
    else:
        slope = 0.0

    return {
        "days_count": int(len(df)),
        "temp_min_overall": round(float(np.min(temp_min_arr)), 2),
        "temp_max_overall": round(float(np.max(temp_max_arr)), 2),
        "temp_mean_overall": round(float(np.mean(temp_mean_arr)), 2),
        "temp_median_overall": round(float(np.median(temp_mean_arr)), 2),
        "temp_std_dev": round(float(np.std(temp_mean_arr, ddof=0)), 2),
        "avg_daily_high": round(float(np.mean(temp_max_arr)), 2),
        "avg_daily_low": round(float(np.mean(temp_min_arr)), 2),
        "avg_diurnal_range": round(float(np.mean(range_arr)), 2),
        "max_diurnal_range": round(float(np.max(range_arr)), 2),
        "total_precipitation": round(float(np.sum(precip_arr)), 2),
        "avg_precipitation": round(float(np.mean(precip_arr)), 2),
        "max_precipitation": round(float(np.max(precip_arr)), 2),
        "rainy_days_count": int(np.sum(precip_arr > 0.1)),
        "max_wind_speed": round(float(np.max(wind_arr)), 2),
        "avg_wind_speed": round(float(np.mean(wind_arr)), 2),
        "warmest_date": df.iloc[warmest_idx]["date"].strftime("%Y-%m-%d"),
        "warmest_temp": round(float(temp_max_arr[warmest_idx]), 2),
        "coolest_date": df.iloc[coolest_idx]["date"].strftime("%Y-%m-%d"),
        "coolest_temp": round(float(temp_min_arr[coolest_idx]), 2),
        "wettest_date": df.iloc[wettest_idx]["date"].strftime("%Y-%m-%d"),
        "wettest_precip": round(float(precip_arr[wettest_idx]), 2),
        "temp_trend_slope": round(slope, 3),
    }


def generate_weather_insights(
    df: pd.DataFrame, stats: dict[str, Any], metadata: dict[str, Any]
) -> list[str]:
    """Produce concise analytical insights from processed weather statistics."""
    insights: list[str] = []

    slope = stats["temp_trend_slope"]
    if slope > 0.15:
        trend_text = f"warming trend (+{slope:.2f} °C/day)"
    elif slope < -0.15:
        trend_text = f"cooling trend ({slope:.2f} °C/day)"
    else:
        trend_text = f"stable thermal profile ({slope:+.2f} °C/day)"

    insights.append(
        f"Temperature Outlook: Across the {stats['days_count']}-day window, daily mean temperatures "
        f"average {stats['temp_mean_overall']:.1f} °C (std dev {stats['temp_std_dev']:.2f} °C) with a {trend_text}."
    )
    insights.append(
        f"Thermal Extremes: Peak daytime temperature reaches {stats['warmest_temp']:.1f} °C on "
        f"{stats['warmest_date']}, while overnight lows dip to {stats['coolest_temp']:.1f} °C on {stats['coolest_date']}."
    )
    insights.append(
        f"Diurnal Variation: Average daily temperature spread is {stats['avg_diurnal_range']:.1f} °C "
        f"(maximum spread {stats['max_diurnal_range']:.1f} °C)."
    )

    if stats["total_precipitation"] > 0.0:
        insights.append(
            f"Precipitation Summary: Cumulative rainfall is {stats['total_precipitation']:.1f} mm across "
            f"{stats['rainy_days_count']} wet day(s), peaking at {stats['wettest_precip']:.1f} mm on {stats['wettest_date']}."
        )
    else:
        insights.append(
            "Precipitation Summary: Dry conditions prevail throughout the forecast window (0.0 mm total precipitation)."
        )

    wind_advisory = "elevated wind activity" if stats["max_wind_speed"] >= 30.0 else "moderate-to-calm winds"
    insights.append(
        f"Wind & Conditions: Peak gusts reach {stats['max_wind_speed']:.1f} km/h (avg {stats['avg_wind_speed']:.1f} km/h), "
        f"indicating {wind_advisory}. Dominant sky condition: {df['weather_description'].mode().iloc[0]}."
    )

    if metadata.get("is_demo"):
        insights.append(
            "Data Notice: These analytics were computed from offline simulated demonstration data, not live API telemetry."
        )

    return insights


class WeatherDataProcessor:
    """Orchestrates weather payload extraction, cleaning, analysis, and optional CSV export."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("autoreport.processor")

    def process(self, payload: dict[str, Any]) -> WeatherAnalytics:
        """Run the full data processing and statistical analysis pipeline."""
        self.logger.info("Starting weather data extraction and cleaning.")
        raw_df = extract_daily_dataframe(payload)
        cleaned_df, quality_metrics = clean_weather_dataframe(raw_df)
        stats = compute_weather_statistics(cleaned_df)
        stats.update(quality_metrics)

        raw_meta = payload.get("metadata", {})
        date_start = cleaned_df["date"].min().strftime("%Y-%m-%d")
        date_end = cleaned_df["date"].max().strftime("%Y-%m-%d")

        metadata = {
            "location_name": raw_meta.get("location_name", "Unknown Location"),
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "elevation": payload.get("elevation"),
            "timezone": payload.get("timezone", "UTC"),
            "source": raw_meta.get("source", "Open-Meteo REST API"),
            "is_demo": bool(raw_meta.get("is_demo", False)),
            "demo_notice": raw_meta.get("demo_notice", ""),
            "fetched_at": raw_meta.get("fetched_at", ""),
            "date_range": f"{date_start} to {date_end}",
            "processed_at": datetime.now(dt_timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

        insights = generate_weather_insights(cleaned_df, stats, metadata)

        self.logger.info(
            "Data processing completed: %d row(s), %d duplicate(s) removed, %d missing value(s) imputed.",
            quality_metrics["cleaned_rows"],
            quality_metrics["duplicates_removed"],
            quality_metrics["missing_values_imputed"],
        )

        return WeatherAnalytics(
            cleaned_df=cleaned_df,
            stats=stats,
            insights=insights,
            metadata=metadata,
        )

    def export_cleaned_data(
        self,
        analytics: WeatherAnalytics,
        output_dir: Path,
        filename: str | None = None,
    ) -> Path:
        """Persist cleaned weather data as a CSV snapshot inside ``data/``."""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_name = filename or f"weather_cleaned_{timestamp}.csv"
            target_path = output_dir / target_name
            export_df = analytics.cleaned_df.copy()
            export_df["date"] = export_df["date"].dt.strftime("%Y-%m-%d")
            export_df.to_csv(target_path, index=False, encoding="utf-8")
            self.logger.info("Saved cleaned dataset to %s", target_path)
            return target_path
        except OSError as exc:
            self.logger.error("Failed to export cleaned data CSV: %s", exc)
            raise DataProcessingError(f"Unable to save cleaned data CSV: {exc}") from exc
