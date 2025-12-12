# fetch_et.py — GDPR fines quarterly export for Power BI (GitHub CSV route)
# VERSION_BANNER: ET_FETCH_V3_2025-12-12

import re
import time
from urllib.parse import urljoin

import pandas as pd
import requests


VERSION_BANNER = "ET_FETCH_V3_2025-12-12"

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
    """
    Extract absolute + relative candidate URLs that might host JSON.
    (More permissive than only 'https://...json' to avoid 0 candidates.)
    """
    candidates = set()

    # absolute URLs that include .json anywhere
    for m in re.findall(r"https?://[^\"'\s>]+", html, flags=re.IGNORECASE):
        m = m.strip().rstrip(");,")
        if ".json" in m.lower() or "/api" in m.lower() or "data" in m.lower():
            candidates.add(m)

    # relative paths containing .json (e.g. /dataXXXX.json)
    for m in re.findall(r"(\/[^\"'\s>]+\.json[^\"'\s>]*)", html, flags=re.IGNORECASE):
        candidates.add(m.strip().rstrip(");,"))

    # also catch bare filenames like dataXXXX.json in JS strings
    for m in re.findall(r"([A-Za-z0-9_\-]+\.json)", html, flags=re.IGNORECASE):
        candidates.add(m.strip().rstrip(");,"))

    # normalize to absolute
    out = []
    for c in candidates:
        if c.lower().startswith("http"):
            out.append(c)
        else:
            out.append(urljoin(BASE_URL, c))
    return sorted(set(out))


def try_fetch_feed(session: requests.Session, url: str) -> dict | None:
    """
    Try URL with cache-busters; accept only dict JSON with 'data' array.
    """
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
    """
    Returns (feed_url, json_dict)
    """
    with requests.Session() as s:
        # warm-up like a browser
        s.get(BASE_URL, headers=BROWSER_HEADERS, timeout=60)
        s.get(INSIGHTS_URL, headers=BROWSER_HEADERS, timeout=60)

        # 1) try default
        js = try_fetch_feed(s, DEFAULT_JSON)
        if js is not None:
            return DEFAULT_JSON, js

        # 2) discover from homepage HTML
        home_html = s.get(BASE_URL, headers=BROWSER_HEADERS, timeout=60).text
        candidates = extract_candidate_urls(home_html)

        print(f"[INFO] Found {len(candidates)} candidate endpoints. Trying...")
        for u in candidates:
            js = try_fetch_feed(s, u)
            if js is not None:
                return u, js

        raise RuntimeError("Could not discover a valid JSON feed endpoint (all candidates returned non-JSON/empty).")


def aggregate_last4(df: pd.DataFrame) -> pd.DataFrame:
    """
    df must have columns: quarter (str), FineEUR (float)
    Returns a 4-row dataframe (last 4 quarters, filled with 0 if missing).
    """
    if df.empty:
        return pd.DataFrame(columns=["quarter", "count_fines", "sum_fines_mln"])

    # ensure chronological order for quarters (Period strings sort ok as 'YYYYQn')
    quarters_sorted = sorted(df["quarter"].unique())
    last4 = quarters_sorted[-4:] if len(quarters_sorted) >= 4 else quarters_sorted

    d = df[df["quarter"].isin(last4)].copy()

    out = (
        d.groupby("quarter", as_index=False)
        .agg(
            count_fines=("FineEUR", "size"),
            sum_fines_mln=("FineEUR", lambda x: x.sum() / 1_000_000.0),
        )
    )

    # Fill missing quarters with 0 (so always stable for Power BI visuals)
    out = out.set_index("quarter").reindex(last4, fill_value=0).reset_index()

    return out[["quarter", "count_fines", "sum_fines_mln"]]


def main():
    print(f"[RUN] {VERSION_BANNER}")

    feed_url, raw = discover_feed()
    print(f"[OK] Using feed: {feed_url}")

    rows = raw.get("data", [])
    df = pd.DataFrame(rows)

    # Map indices as per your original approach: 2=Country, 4=Date, 5=Fine, 7=Sector
    needed = {2: "Country", 4: "DateText", 5: "FineText", 7: "Sector"}
    for idx in needed:
        if idx not in df.columns:
            raise RuntimeError(f"Expected column index {idx} missing. Got columns: {list(df.columns)[:30]}")

    df = df.rename(columns=needed)[["Country", "DateText", "FineText", "Sector"]]

    df["Date"] = pd.to_datetime(df["DateText"], errors="coerce")
    df = df.dropna(subset=["Date"])

    df["FineEUR"] = df["FineText"].map(parse_eur_amount)
    df = df.dropna(subset=["FineEUR"])

    # IMPORTANT: quarter is an explicit column (no index tricks)
    df["quarter"] = df["Date"].dt.to_period("Q").astype(str)

    mask_fin = df["Sector"].astype(str).str.contains("finance", case=False, na=False)
    mask_nl = df["Country"].astype(str).str.contains("netherlands", case=False, na=False)

    fin = aggregate_last4(df[mask_fin])
    fin["dim"] = "Finance"

    nl = aggregate_last4(df[mask_fin & mask_nl])
    nl["dim"] = "NL_Finance"

    out = pd.concat([fin, nl], ignore_index=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print(f"Saved {OUT_CSV} ({len(out)} rows)")


if __name__ == "__main__":
    main()
