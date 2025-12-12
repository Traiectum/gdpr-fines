# fetch_et.py — GDPR fines quarterly export for Power BI (GitHub CSV route)
# VERSION_BANNER: ET_FETCH_V4_FILL_LAST4_2025-12-12

import re
import time
from urllib.parse import urljoin

import pandas as pd
import requests


VERSION_BANNER = "ET_FETCH_V4_FILL_LAST4_2025-12-12"

BASE_URL = "https://www.enforcementtracker.com/"
INSIGHTS_URL = "https://www.enforcementtracker.com/?insights"
DEFAULT_JSON = "https://www.enforcementtracker.com/data.json"

OUT_CSV = "gdpr_fines_quarterly_last4.csv"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

JSON_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Referer": INSIGHTS_URL,
    "Origin": "https://www.enforcementtracker.com",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def parse_eur_amount(value):
    """Parse euro-like values to float EUR. Keeps digits only."""
    if value is None:
        return None
    s = re.sub(r"[^\d]", "", str(value))
    return float(s) if s else None


def looks_like_json(resp: requests.Response) -> bool:
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "json" in ct:
        return True
    if "text/plain" in ct:
        t = (resp.text or "").lstrip()
        return t.startswith("{") or t.startswith("[")
    return False


def extract_candidate_urls(html: str) -> list[str]:
    candidates = set()

    for m in re.findall(r"https?://[^\"'\s>]+", html, flags=re.IGNORECASE):
        m = m.strip().rstrip(");,")
        if ".json" in m.lower() or "/api" in m.lower() or "data" in m.lower():
            candidates.add(m)

    for m in re.findall(r"(\/[^\"'\s>]+\.json[^\"'\s>]*)", html, flags=re.IGNORECASE):
        candidates.add(m.strip().rstrip(");,"))

    for m in re.findall(r"([A-Za-z0-9_\-]+\.json)", html, flags=re.IGNORECASE):
        candidates.add(m.strip().rstrip(");,"))

    out = []
    for c in candidates:
        out.append(c if c.lower().startswith("http") else urljoin(BASE_URL, c))
    return sorted(set(out))


def try_fetch_feed(session: requests.Session, url: str) -> dict | None:
    ts = int(time.time())
    urls = [url]
    if "?" in url:
        urls += [f"{url}&_={ts}", f"{url}&v={ts}"]
    else:
        urls += [f"{url}?_={ts}", f"{url}?v={ts}"]

    for u in urls:
        r = session.get(u, headers=JSON_HEADERS, timeout=60, allow_redirects=True)
        if not looks_like_json(r):
            continue
        try:
            js = r.json()
        except Exception:
            continue
        if isinstance(js, dict) and isinstance(js.get("data"), list) and len(js["data"]) > 0:
            return js
    return None


def discover_feed() -> tuple[str, dict]:
    with requests.Session() as s:
        s.get(BASE_URL, headers=BROWSER_HEADERS, timeout=60)
        s.get(INSIGHTS_URL, headers=BROWSER_HEADERS, timeout=60)

        js = try_fetch_feed(s, DEFAULT_JSON)
        if js is not None:
            return DEFAULT_JSON, js

        home_html = s.get(BASE_URL, headers=BROWSER_HEADERS, timeout=60).text
        candidates = extract_candidate_urls(home_html)

        print(f"[INFO] Found {len(candidates)} candidate endpoints. Trying...")
        for u in candidates:
            js = try_fetch_feed(s, u)
            if js is not None:
                return u, js

        raise RuntimeError("Could not discover a valid JSON feed endpoint.")


def last4_quarter_list(df_all: pd.DataFrame) -> list[str]:
    """
    Determine the global last 4 quarters from the full dataset.
    Returns list like ["2025Q1","2025Q2","2025Q3","2025Q4"] (ascending).
    """
    if df_all.empty:
        return []

    # Use Period for reliable ordering
    q_period = df_all["Date"].dt.to_period("Q")
    max_q = q_period.max()
    last4 = pd.period_range(max_q - 3, max_q, freq="Q")
    return [str(p) for p in last4]


def aggregate_for_dim(df_dim: pd.DataFrame, quarters_last4: list[str]) -> pd.DataFrame:
    """
    Always returns exactly 4 rows (for the given quarter list), filling missing with zeros.
    """
    if not quarters_last4:
        return pd.DataFrame(columns=["quarter", "count_fines", "sum_fines_mln"])

    if df_dim.empty:
        # return all zeros
        return pd.DataFrame(
            {
                "quarter": quarters_last4,
                "count_fines": [0] * 4,
                "sum_fines_mln": [0.0] * 4,
            }
        )

    df_dim = df_dim.copy()
    df_dim["quarter"] = df_dim["Date"].dt.to_period("Q").astype(str)

    agg = (
        df_dim.groupby("quarter", as_index=False)
        .agg(
            count_fines=("FineEUR", "size"),
            sum_fines_mln=("FineEUR", lambda x: x.sum() / 1_000_000.0),
        )
    )

    # fill missing quarters with 0
    agg = agg.set_index("quarter").reindex(quarters_last4, fill_value=0).reset_index()

    # ensure numeric types
    agg["count_fines"] = agg["count_fines"].astype(int)
    agg["sum_fines_mln"] = agg["sum_fines_mln"].astype(float)

    return agg[["quarter", "count_fines", "sum_fines_mln"]]


def main():
    print(f"[RUN] {VERSION_BANNER}")

    feed_url, raw = discover_feed()
    print(f"[OK] Using feed: {feed_url}")

    rows = raw.get("data", [])
    df = pd.DataFrame(rows)

    # 2=Country, 4=Date, 5=Fine, 7=Sector
    needed = {2: "Country", 4: "DateText", 5: "FineText", 7: "Sector"}
    for idx in needed:
        if idx not in df.columns:
            raise RuntimeError(f"Expected column index {idx} missing. Got columns: {list(df.columns)[:30]}")

    df = df.rename(columns=needed)[["Country", "DateText", "FineText", "Sector"]]

    df["Date"] = pd.to_datetime(df["DateText"], errors="coerce")
    df = df.dropna(subset=["Date"])

    df["FineEUR"] = df["FineText"].map(parse_eur_amount)
    df = df.dropna(subset=["FineEUR"])

    # Determine global last 4 quarters (from all cases, not just finance)
    quarters_last4 = last4_quarter_list(df)
    if len(quarters_last4) != 4:
        raise RuntimeError("Could not determine last 4 quarters from dataset.")

    mask_fin = df["Sector"].astype(str).str.contains("finance", case=False, na=False)
    mask_nl = df["Country"].astype(str).str.contains("netherlands", case=False, na=False)

    fin = aggregate_for_dim(df[mask_fin], quarters_last4)
    fin["dim"] = "Finance"

    nl = aggregate_for_dim(df[mask_fin & mask_nl], quarters_last4)
    nl["dim"] = "NL_Finance"

    out = pd.concat([fin, nl], ignore_index=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print(f"Saved {OUT_CSV} ({len(out)} rows)")
    print(f"[INFO] Quarters used: {', '.join(quarters_last4)}")


if __name__ == "__main__":
    main()
