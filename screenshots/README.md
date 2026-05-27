# Screenshots

The screenshots in this folder back the README and the demo. The walkthrough only needs five images; capture them in order so they tell a coherent story.

## Capture checklist

1. `01_overview.png` -- the dashboard overview after running analysis. Tiles, severity breakdown, source breakdown.
2. `02_issues_list.png` -- the filtered issues table with at least one filter applied (for example, Severity = CRITICAL).
3. `03_detail.png` -- the detail view of a single issue showing the AI summary and the suggested root cause.
4. `04_trend.png` -- the trends tab with at least one anomaly day marked with a red dashed line.
5. `05_digest.png` -- the rendered email digest as it appears in an HTML email client.

## How to capture

Streamlit screens:

- Windows: `Win + Shift + S`, then save to this folder with the name above.
- macOS: `Cmd + Shift + 4`, drag the area, then move the file here.

Email digest:

- Send the digest to yourself with `python scripts/send_digest.py` or open the rendered HTML from stdout in a browser.
- Take a screenshot of the rendered email.

## Notes

- Do not include any real credentials or PII in screenshots. The mock data is safe; do not commit screenshots taken against a production environment.
- PNGs in this folder are gitignored by default. If you want to ship them with the repo for a recruiter, remove them from `.gitignore` after confirming they are clean.
