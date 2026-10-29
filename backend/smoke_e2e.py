"""Manual end-to-end smoke run against the local API (real models)."""
from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

BASE = "http://127.0.0.1:8765"
HEADERS = {"x-vts-client": "web"}
sample = Path(__file__).resolve().parents[1] / "samples" / "sample_en.mp4"


def main() -> None:
    with TestClient(app, base_url=BASE) as client:
        with open(sample, "rb") as handle:
            response = client.post(
                "/api/projects", headers=HEADERS,
                files={"file": ("sample_en.mp4", handle, "video/mp4")},
                data={"name": "Prueba E2E"},
            )
        print("upload", response.status_code, response.json())
        response.raise_for_status()
        project = response.json()

        response = client.post(
            f"/api/projects/{project['id']}/jobs", headers=HEADERS,
            json={"source_language": "en", "voice": "es_MX-ald-medium",
                  "mode": "replace_dialogue", "preset": "balanced",
                  "separation": False, "threads": 3},
        )
        print("job", response.status_code, response.json())
        response.raise_for_status()
        job_id = response.json()["id"]

        last = None
        deadline = time.time() + 1800
        while time.time() < deadline:
            job = client.get(f"/api/jobs/{job_id}").json()
            marker = (job["status"], job["stage"], round(job["progress"]))
            if marker != last:
                print(marker, job.get("message"))
                last = marker
            if job["status"] in ("completed", "failed", "cancelled", "interrupted"):
                break
            time.sleep(2)

        job = client.get(f"/api/jobs/{job_id}").json()
        print("FINAL", job["status"], job.get("error"), job.get("error_hint"))
        print("STATS", job.get("stats"))
        print("WARNINGS", job.get("warnings"))
        events = client.get(f"/api/jobs/{job_id}/events").json()["events"]
        for event in events[-25:]:
            print("EVENT", event["level"], event["message"])

        segments = client.get(f"/api/jobs/{job_id}/segments").json()["segments"]
        for segment in segments:
            print(f"  [{segment['start']:.2f}-{segment['end']:.2f}] "
                  f"{segment['text_src']} -> {segment['text_es']} ({segment['status']})")
        if job["status"] == "completed":
            out = client.get(f"/api/jobs/{job_id}/download")
            print("download", out.status_code, len(out.content), out.headers.get("content-type"))
            srt = client.get(f"/api/jobs/{job_id}/subtitles/srt")
            print("srt", srt.status_code, srt.text[:300])


if __name__ == "__main__":
    main()
