"""Scraper SUSEP — varre a API pública de corretores e retorna a base completa."""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://www2.susep.gov.br/safe/corretoresapig/dadospublicos/pesquisar"


def make_session():
    s = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=40, pool_maxsize=40))
    s.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    return s


def fetch_page(session, page):
    r = session.get(BASE, params={"page": page}, timeout=30, verify=False)
    r.raise_for_status()
    return r.json()


def scrape_all(workers=10, on_progress=None):
    """Scrape full SUSEP base. Returns list of records."""
    session = make_session()
    probe = fetch_page(session, 1)
    total = probe["retorno"]["totalRegistros"]
    page_size = probe["retorno"]["tamanhoPagina"]
    total_pages = (total + page_size - 1) // page_size

    if on_progress:
        on_progress(f"Total records: {total:,} | pages: {total_pages:,}")

    pages_data = {1: probe["retorno"]["registros"]}
    errors = []
    start = time.time()
    done = 1

    def _fetch(p):
        try:
            return p, fetch_page(session, p)["retorno"]["registros"], None
        except Exception as e:
            return p, None, f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_fetch, p): p for p in range(2, total_pages + 1)}
        for fut in as_completed(futs):
            page, recs, err = fut.result()
            done += 1
            if err:
                errors.append((page, err))
            else:
                pages_data[page] = recs
            if on_progress and (done % 500 == 0 or done == total_pages):
                elapsed = time.time() - start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total_pages - done) / rate if rate > 0 else 0
                on_progress(f"  {done}/{total_pages} ({100*done/total_pages:.1f}%) | {rate:.1f}/s | ETA {eta/60:.1f}min | errs={len(errors)}")

    # Retry errors sequentially
    for page, _ in list(errors):
        try:
            pages_data[page] = fetch_page(session, page)["retorno"]["registros"]
            errors = [(p, e) for p, e in errors if p != page]
        except Exception:
            pass

    all_records = []
    for p in sorted(pages_data.keys()):
        all_records.extend(pages_data[p])

    if on_progress:
        on_progress(f"Scrape complete: {len(all_records):,} records | errors remaining: {len(errors)}")

    return all_records, errors
