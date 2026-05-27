@echo off
REM Daily OpsLens job: run analysis, then send the digest.
REM Wire this into Windows Task Scheduler to fire at 08:30 every morning.
cd /d "d:\.projects\AI-powered assistant\opslens"
python scripts\run_analysis.py >> logs\daily.log 2>&1
python scripts\send_digest.py >> logs\daily.log 2>&1
