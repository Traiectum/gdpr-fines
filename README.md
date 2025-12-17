# GDPR Fines – Automated Power BI Data Feed

This repository contains an **automated data pipeline** that fetches GDPR enforcement fine data, aggregates it by quarter, and publishes a **stable CSV feed** for use in **Power BI dashboards**.

The solution is designed to run **fully automatically**, without manual intervention.

---

## What this does

- Fetches GDPR fine data from the public *Enforcement Tracker* website
- Aggregates fines:
  - by **quarter**
  - for **Finance** and **NL_Finance**
- Always outputs the **latest 4 quarters**
- Fills missing quarters with **0 values** (no data gaps)
- Publishes a **stable CSV** that Power BI can refresh against
- Updates GitHub **only when the data actually changes**

---

## Output (for Power BI)

Power BI should always connect to this file: https://raw.githubusercontent.com/Traiectum/gdpr-fines/main/current/gdpr_fines_current.csv

