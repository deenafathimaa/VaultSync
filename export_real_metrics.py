import csv
import argparse
import math
from collections import defaultdict
from pathlib import Path

import mysql.connector


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "deena@1604",
    "database": "secure_file_sharing",
}

BASE_DIR = Path(__file__).resolve().parent
METRICS_CSV = BASE_DIR / "metrics_template.csv"
EVENTS_CSV = BASE_DIR / "security_events_template.csv"


def safe_avg(values):
    if not values:
        return math.nan
    return sum(values) / len(values)


def _minutes_filter_clause(lookback_minutes):
    if lookback_minutes is None:
        return "", []
    return " AND created_at >= (NOW() - INTERVAL %s MINUTE)", [lookback_minutes]


def fetch_client_metric(cursor, metric_name, mode, lookback_minutes=None):
    time_clause, time_params = _minutes_filter_clause(lookback_minutes)
    cursor.execute(
        f"""
        SELECT ROUND(file_size_mb, 3) AS size_key, duration_ms
        FROM performance_metrics
        WHERE metric_name = %s
          AND mode = %s
          AND status = 'success'
          AND file_size_mb IS NOT NULL
          AND duration_ms IS NOT NULL
          {time_clause}
        """,
        [metric_name, mode] + time_params,
    )

    grouped = defaultdict(list)
    for size_key, duration_ms in cursor.fetchall():
        grouped[float(size_key)].append(float(duration_ms) / 1000.0)

    return {k: safe_avg(v) for k, v in grouped.items()}


def fetch_storage_sizes(cursor, lookback_minutes=None):
    time_clause, time_params = _minutes_filter_clause(lookback_minutes)
    cursor.execute(
        f"""
        SELECT ROUND(size_before_mb, 3) AS size_key,
               AVG(size_before_mb),
               AVG(size_after_mb)
        FROM performance_metrics
        WHERE metric_name = 'upload_server'
          AND mode = 'encrypted'
          AND status = 'success'
          AND size_before_mb IS NOT NULL
          AND size_after_mb IS NOT NULL
                    {time_clause}
        GROUP BY ROUND(size_before_mb, 3)
        ORDER BY size_key
                """,
                time_params,
    )

    before_map = {}
    after_map = {}
    for size_key, before_avg, after_avg in cursor.fetchall():
        key = float(size_key)
        before_map[key] = float(before_avg)
        after_map[key] = float(after_avg)

    return before_map, after_map


def fetch_request_timing(cursor, lookback_minutes=None):
    output = {
        "approve_total_ms": math.nan,
        "reject_request_ms": math.nan,
        "download_authorized_ms": math.nan,
        "download_unauthorized_ms": math.nan,
    }

    time_clause, time_params = _minutes_filter_clause(lookback_minutes)

    for metric_name, out_key in [
        ("approve_total", "approve_total_ms"),
        ("reject_request", "reject_request_ms"),
        ("download_authorized", "download_authorized_ms"),
        ("download_unauthorized", "download_unauthorized_ms"),
    ]:
        cursor.execute(
            f"""
            SELECT AVG(duration_ms)
            FROM performance_metrics
            WHERE metric_name = %s
              AND status IS NOT NULL
              AND duration_ms IS NOT NULL
              {time_clause}
            """,
            [metric_name] + time_params,
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            output[out_key] = float(row[0])

    if math.isnan(output["approve_total_ms"]):
        cursor.execute(
            f"""
            SELECT AVG(duration_ms)
            FROM performance_metrics
            WHERE metric_name = %s
              AND status IS NOT NULL
              AND duration_ms IS NOT NULL
              {time_clause}
            """,
            ["approve_request"] + time_params,
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            output["approve_total_ms"] = float(row[0])
            print("Using legacy approve_request metric as a temporary fallback.")

    return output


def fetch_security_events(cursor):
    def count_actions(actions):
        placeholders = ",".join(["%s"] * len(actions))
        cursor.execute(
            f"SELECT COUNT(*) FROM logs WHERE action IN ({placeholders})",
            tuple(actions),
        )
        return int(cursor.fetchone()[0])

    successful_access = count_actions(["download", "upload", "access_approved"])
    denied_access = count_actions(["denied_no_access"])
    expired_access = count_actions(["denied_expired"])
    rejected_access = count_actions(["access_rejected"])

    return [
        ("successful_access", successful_access),
        ("denied_access", denied_access),
        ("expired_access", expired_access),
        ("rejected_access", rejected_access),
    ]


def write_metrics_csv(rows):
    headers = [
        "file_size_mb",
        "upload_non_encrypted_s",
        "upload_encrypted_s",
        "download_open_non_encrypted_s",
        "download_open_encrypted_s",
        "size_before_mb",
        "size_after_mb",
        "approve_total_ms",
        "reject_request_ms",
        "download_authorized_ms",
        "download_unauthorized_ms",
    ]

    with METRICS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_events_csv(rows):
    with EVENTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["event", "count"])
        writer.writerows(rows)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export real metrics for chart generation."
    )
    parser.add_argument(
        "--lookback-minutes",
        type=int,
        default=30,
        help="Only include records from the last N minutes (default: 30).",
    )
    parser.add_argument(
        "--all-data",
        action="store_true",
        help="Ignore lookback and include all historical records.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    lookback_minutes = None if args.all_data else args.lookback_minutes

    if lookback_minutes is not None and lookback_minutes <= 0:
        raise ValueError("--lookback-minutes must be a positive integer")

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(buffered=True)

    upload_enc = fetch_client_metric(cursor, "upload_total", "encrypted", lookback_minutes)
    upload_plain = fetch_client_metric(cursor, "upload_total", "non_encrypted", lookback_minutes)
    download_enc = fetch_client_metric(cursor, "download_open_total", "encrypted", lookback_minutes)
    download_plain = fetch_client_metric(cursor, "download_open_total", "non_encrypted", lookback_minutes)

    size_before_map, size_after_map = fetch_storage_sizes(cursor, lookback_minutes)
    request_timing = fetch_request_timing(cursor, lookback_minutes)
    event_rows = fetch_security_events(cursor)

    keys = set()
    keys.update(upload_enc.keys())
    keys.update(upload_plain.keys())
    keys.update(download_enc.keys())
    keys.update(download_plain.keys())
    keys.update(size_before_map.keys())

    if not keys:
        keys = {1.0, 5.0, 10.0, 25.0, 50.0, 100.0}

    sorted_keys = sorted(keys)

    metric_rows = []
    for key in sorted_keys:
        metric_rows.append(
            {
                "file_size_mb": key,
                "upload_non_encrypted_s": upload_plain.get(key, math.nan),
                "upload_encrypted_s": upload_enc.get(key, math.nan),
                "download_open_non_encrypted_s": download_plain.get(key, math.nan),
                "download_open_encrypted_s": download_enc.get(key, math.nan),
                "size_before_mb": size_before_map.get(key, key),
                "size_after_mb": size_after_map.get(key, math.nan),
                "approve_total_ms": request_timing["approve_total_ms"],
                "reject_request_ms": request_timing["reject_request_ms"],
                "download_authorized_ms": request_timing["download_authorized_ms"],
                "download_unauthorized_ms": request_timing["download_unauthorized_ms"],
            }
        )

    # Keep only fully populated rows so the chart set reflects complete real runs.
    complete_rows = [
        row
        for row in metric_rows
        if not any(
            math.isnan(row[field])
            for field in (
                "upload_non_encrypted_s",
                "upload_encrypted_s",
                "download_open_non_encrypted_s",
                "download_open_encrypted_s",
                "size_before_mb",
                "size_after_mb",
                "approve_total_ms",
            )
        )
    ]

    if complete_rows:
        metric_rows = complete_rows

    write_metrics_csv(metric_rows)
    write_events_csv(event_rows)

    cursor.close()
    conn.close()

    print("Real metrics exported successfully.")
    if lookback_minutes is None:
        print("Using all historical performance metrics.")
    else:
        print(f"Using performance metrics from last {lookback_minutes} minutes.")
    print(f"Updated: {METRICS_CSV}")
    print(f"Updated: {EVENTS_CSV}")


if __name__ == "__main__":
    main()
