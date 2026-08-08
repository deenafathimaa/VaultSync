import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt


BASE_DIR = Path(__file__).resolve().parent
METRICS_CSV = BASE_DIR / "metrics_template.csv"
EVENTS_CSV = BASE_DIR / "security_events_template.csv"
OUTPUT_DIR = BASE_DIR / "charts"


def _read_metrics(path: Path):
    rows = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "file_size_mb": float(row["file_size_mb"]),
                    "upload_non_encrypted_s": float(row["upload_non_encrypted_s"]),
                    "upload_encrypted_s": float(row["upload_encrypted_s"]),
                    "download_open_non_encrypted_s": float(row["download_open_non_encrypted_s"]),
                    "download_open_encrypted_s": float(row["download_open_encrypted_s"]),
                    "size_before_mb": float(row["size_before_mb"]),
                    "size_after_mb": float(row["size_after_mb"]),
                    "approve_total_ms": float(row["approve_total_ms"]),
                    "reject_request_ms": float(row["reject_request_ms"]),
                    "download_authorized_ms": float(row["download_authorized_ms"]),
                    "download_unauthorized_ms": float(row["download_unauthorized_ms"]),
                }
            )

    rows.sort(key=lambda x: x["file_size_mb"])
    return rows


def _read_events(path: Path):
    labels = []
    values = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            labels.append(row["event"].replace("_", " ").title())
            values.append(float(row["count"]))
    return labels, values


def plot_upload_time(rows):
    x = [r["file_size_mb"] for r in rows]
    y_plain = [r["upload_non_encrypted_s"] for r in rows]
    y_enc = [r["upload_encrypted_s"] for r in rows]

    plt.figure(figsize=(9, 5))
    plt.plot(x, y_plain, marker="o", linewidth=2, label="Non-encrypted")
    plt.plot(x, y_enc, marker="o", linewidth=2, label="Encrypted")
    plt.title("File Size vs Processing Time")
    plt.xlabel("File Size (MB)")
    plt.ylabel("Processing Time (s)")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "line_upload_time.png", dpi=200)
    plt.close()


def plot_encryption_overhead_percent(rows):
    valid_rows = [
        r
        for r in rows
        if not math.isnan(r["size_before_mb"])
        and not math.isnan(r["size_after_mb"])
        and r["size_before_mb"] > 0
    ]

    if not valid_rows:
        print("Skipping overhead chart: no rows with valid storage sizes.")
        return

    x = [r["file_size_mb"] for r in valid_rows]
    overhead_pct = [
        ((r["size_after_mb"] - r["size_before_mb"]) / r["size_before_mb"]) * 100
        for r in valid_rows
    ]

    plt.figure(figsize=(9, 5))
    plt.plot(x, overhead_pct, marker="o", linewidth=2, label="Overhead %")
    plt.axhline(0, color="gray", linewidth=1, alpha=0.6)
    plt.title("Encryption Storage Overhead (%) vs File Size")
    plt.xlabel("File Size (MB)")
    plt.ylabel("Overhead (%)")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "line_storage_overhead_percent.png", dpi=200)
    plt.close()


def plot_download_open_time(rows):
    x = [r["file_size_mb"] for r in rows]
    y_plain = [r["download_open_non_encrypted_s"] for r in rows]
    y_enc = [r["download_open_encrypted_s"] for r in rows]

    plt.figure(figsize=(9, 5))
    plt.plot(x, y_plain, marker="o", linewidth=2, label="Non-encrypted")
    plt.plot(x, y_enc, marker="o", linewidth=2, label="Encrypted")
    plt.title("File Size vs Download + Open Time")
    plt.xlabel("File Size (MB)")
    plt.ylabel("Download + Open Time (s)")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "line_download_open_time.png", dpi=200)
    plt.close()


def plot_storage_overhead(rows):
    valid_rows = [
        r
        for r in rows
        if not math.isnan(r["size_after_mb"]) and not math.isnan(r["size_before_mb"])
    ]

    if not valid_rows:
        print("Skipping storage overhead chart: no rows with both size_before_mb and size_after_mb.")
        return

    labels = [f'{r["file_size_mb"]:.3f}'.rstrip("0").rstrip(".") for r in valid_rows]
    before = [r["size_before_mb"] for r in valid_rows]
    after = [r["size_after_mb"] for r in valid_rows]

    x = list(range(len(labels)))
    width = 0.38

    plt.figure(figsize=(10, 5))
    plt.bar([i - width / 2 for i in x], before, width=width, label="Before encryption")
    plt.bar([i + width / 2 for i in x], after, width=width, label="After encryption")
    plt.xticks(x, labels)
    plt.title("Storage Size Before vs After Encryption")
    plt.xlabel("File Size (MB)")
    plt.ylabel("Stored Size (MB)")
    plt.legend()
    plt.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "bar_storage_overhead.png", dpi=200)
    plt.close()


def plot_request_handling(rows):
    metrics = {
        "Approve request": [r["approve_total_ms"] for r in rows],
        "Reject request": [r["reject_request_ms"] for r in rows],
        "Download authorized": [r["download_authorized_ms"] for r in rows],
        "Download unauthorized": [r["download_unauthorized_ms"] for r in rows],
    }

    labels = list(metrics.keys())
    averages = [sum(v) / len(v) for v in metrics.values()]

    plt.figure(figsize=(9, 5))
    bars = plt.bar(labels, averages)
    plt.title("Average Request Handling Time")
    plt.ylabel("Time (ms)")
    plt.grid(axis="y", alpha=0.25)

    for bar, value in zip(bars, averages):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1,
            f"{value:.1f}",
            ha="center",
            va="bottom",
        )

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "bar_request_handling_time.png", dpi=200)
    plt.close()


def plot_security_events(labels, values):
    filtered = [(label, value) for label, value in zip(labels, values) if value > 0]
    if not filtered:
        print("Skipping security events chart: no non-zero events.")
        return

    labels, values = zip(*filtered)

    plt.figure(figsize=(7, 7))
    plt.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    plt.title("Security Event Distribution")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "pie_security_events.png", dpi=200)
    plt.close()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    metrics_rows = _read_metrics(METRICS_CSV)
    event_labels, event_values = _read_events(EVENTS_CSV)

    plot_upload_time(metrics_rows)
    plot_encryption_overhead_percent(metrics_rows)
    plot_download_open_time(metrics_rows)
    plot_storage_overhead(metrics_rows)
    plot_request_handling(metrics_rows)
    plot_security_events(event_labels, event_values)

    print("Charts generated successfully.")
    print(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
