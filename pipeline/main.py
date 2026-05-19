"""
Orquestrador do pipeline diário.

Fluxo:
  1. Scrape SUSEP (~15-60 min em GH Actions com 20 workers)
  2. Carrega known_ids.txt.gz e detection_history.json.gz (snapshot anterior)
  3. Identifica novos: corretorId presente hoje, ausente ontem, situacao=Ativo
  4. Enriquece novos via CNPJ.ws + fallbacks
  5. Filtra UF=MG
  6. Se há novos MG, gera HTML interativo e envia email com HTML anexo
  7. Salva state (known_ids + detection_history) — committado pelo workflow
"""
import gzip
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.scrape import scrape_all  # noqa: E402
from pipeline.enrich import enrich_many  # noqa: E402
from pipeline.notify import send_email  # noqa: E402
from pipeline.render_html import render as render_html  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
STATE = REPO / "state"
OUT = REPO / "output"
STATE.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

KNOWN_IDS = STATE / "known_ids.txt.gz"
DETECTION_HISTORY = STATE / "detection_history.json.gz"
LAST_RUN = STATE / "last_run.json"

UF_FILTER = os.environ.get("UF_FILTER", "MG").upper()
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def load_known_ids():
    if not KNOWN_IDS.exists():
        return set()
    with gzip.open(KNOWN_IDS, "rt", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_known_ids(ids):
    with gzip.open(KNOWN_IDS, "wt", encoding="utf-8") as f:
        for i in sorted(ids):
            f.write(i + "\n")


def load_detection_history():
    """Map corretorId -> first_seen_date ('' for baseline, 'YYYY-MM-DD' for detected)."""
    if not DETECTION_HISTORY.exists():
        return {}
    with gzip.open(DETECTION_HISTORY, "rt", encoding="utf-8") as f:
        return json.load(f)


def save_detection_history(history):
    with gzip.open(DETECTION_HISTORY, "wt", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, separators=(",", ":"))


def build_email_html_summary(new_mg, run_date, total_records, total_active, total_new):
    """HTML do CORPO do email (resumo curto). O HTML interativo vai como anexo."""
    rows = []
    for r in new_mg[:20]:  # primeiros 20 no corpo, resto no anexo
        email_html = f'<a href="mailto:{r.get("email","")}">{r.get("email","")}</a>' if r.get("email") else "—"
        tel = r.get("telefone", "") or "—"
        rows.append(
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #eee'>{(r.get('nome') or '').strip()}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee'>{r.get('municipio','')}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;font-family:monospace'>{tel}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee'>{email_html}</td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)
    extra = ""
    if len(new_mg) > 20:
        extra = f"<p style='color:#666;font-size:13px'>+{len(new_mg)-20} outros corretores no HTML em anexo.</p>"
    return f"""<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;background:#f5f5f7;padding:24px;margin:0">
<div style="max-width:720px;margin:0 auto;background:white;padding:32px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.05)">
<h2 style="margin:0 0 8px;color:#111">🆕 {len(new_mg)} novos corretores em {UF_FILTER}</h2>
<p style="color:#666;margin:0 0 24px">Detectados no scan de {run_date}.</p>

<div style="background:#f5f5f7;border-radius:8px;padding:16px;margin-bottom:24px;font-size:14px">
  <strong>📎 Abra o HTML anexo</strong> para ver a lista completa com filtros por cidade, busca, e botões diretos de WhatsApp/Email para cada corretor.
</div>

<h3 style="margin:0 0 12px;color:#111;font-size:16px">Preview dos primeiros {min(20, len(new_mg))}:</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px">
<thead style="background:#f9f9fb"><tr>
  <th style="text-align:left;padding:10px 8px;border-bottom:2px solid #ddd">Nome</th>
  <th style="text-align:left;padding:10px 8px;border-bottom:2px solid #ddd">Cidade</th>
  <th style="text-align:left;padding:10px 8px;border-bottom:2px solid #ddd">Telefone</th>
  <th style="text-align:left;padding:10px 8px;border-bottom:2px solid #ddd">Email</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
{extra}

<div style="margin-top:32px;padding-top:16px;border-top:1px solid #eee;color:#999;font-size:12px">
  Total escaneado hoje: {total_records:,} · Ativos: {total_active:,} · Novos desde último scan: {total_new}<br>
  Pipeline automático Synkra · base pública SUSEP · enriquecimento Receita Federal
</div>
</div>
</body></html>"""


def main():
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_date = datetime.now().strftime("%Y-%m-%d")
    log(f"=== Pipeline run {run_id} | UF={UF_FILTER} | dry_run={DRY_RUN} ===")

    log("Step 1/6: Scrape SUSEP")
    records, errors = scrape_all(workers=20, on_progress=log)
    if errors:
        log(f"WARN: {len(errors)} pages failed after retries")
    if len(records) < 100000:
        log(f"ABORT: only {len(records)} records returned (expected >150k).")
        return 1

    log("Step 2/6: Load state")
    known = load_known_ids()
    history = load_detection_history()
    log(f"  known_ids previous: {len(known):,} | history entries: {len(history):,}")

    today_active = [r for r in records if r.get("situacao") == "Ativo"]
    today_ids = set(r["corretorId"] for r in today_active)
    log(f"  active today: {len(today_active):,}")

    log("Step 3/6: Detect new ids + update history")
    is_first_run = len(known) == 0
    if is_first_run:
        log("  FIRST RUN: marking all current ids as 'pré-baseline' (empty date)")
        for r in today_active:
            history.setdefault(r["corretorId"], "")
        new_records = []
    else:
        new_ids = today_ids - known
        new_records = [r for r in today_active if r["corretorId"] in new_ids]
        for r in new_records:
            history[r["corretorId"]] = run_date  # registra data da detecção
    log(f"  new since last run: {len(new_records)} | history now: {len(history)}")

    log("Step 4/6: Enrich + filter UF")
    new_mg = []
    if new_records:
        pj_new = [r for r in new_records if "*" not in (r.get("cpfCnpj") or "")]
        log(f"  PJ to enrich: {len(pj_new)} (PF skipped: {len(new_records)-len(pj_new)})")
        enriched = enrich_many(pj_new, delay=4.0, on_log=log)
        # anexa detected_at em cada enriched record
        for r in enriched:
            r["detected_at"] = run_date
        new_mg = [r for r in enriched if (r.get("uf") or "").upper() == UF_FILTER]
        log(f"  enriched {len(enriched)} | UF={UF_FILTER}: {len(new_mg)}")

    log("Step 5/6: Render HTML + notify")
    if new_mg and not DRY_RUN:
        html_path = OUT / f"novos_{UF_FILTER}_{run_id}.html"
        size = render_html(new_mg, html_path, uf_filter=UF_FILTER,
                           title_extra=f"detectados em {run_date}")
        log(f"  HTML rendered: {html_path.name} ({size:,} bytes)")

        subject = f"[SUSEP {UF_FILTER}] {len(new_mg)} novos corretores — {run_date}"
        body = (
            f"{len(new_mg)} novos corretores em {UF_FILTER} desde o último scan.\n\n"
            "Abra o HTML em anexo para ver a lista completa com filtros e botões de contato.\n\n"
            f"Total escaneado: {len(records):,}\n"
            f"Ativos hoje: {len(today_active):,}\n"
            f"Novos desde último scan: {len(new_records)}\n\n"
            "-- Pipeline Synkra SUSEP\n"
        )
        body_html = build_email_html_summary(
            new_mg, run_date, len(records), len(today_active), len(new_records)
        )
        try:
            n = send_email(subject, body, attachments=[html_path], html=body_html)
            log(f"  email sent to {n} recipient(s)")
        except Exception as e:
            log(f"  EMAIL FAILED: {type(e).__name__}: {e}")
    elif new_mg and DRY_RUN:
        log(f"  DRY_RUN — would have emailed {len(new_mg)} new {UF_FILTER}")
    else:
        log(f"  no new {UF_FILTER} — skipping email (per requirement)")

    log("Step 6/6: Persist state")
    save_known_ids(today_ids)
    save_detection_history(history)
    LAST_RUN.write_text(json.dumps({
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "total_records": len(records),
        "active_today": len(today_active),
        "new_since_last": len(new_records),
        f"new_{UF_FILTER}": len(new_mg),
        "scrape_errors": len(errors),
        "history_size": len(history),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log("=== Pipeline done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
