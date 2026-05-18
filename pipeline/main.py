"""
Orquestrador do pipeline diário.

Fluxo:
  1. Scrape SUSEP (~5-15 min em GH Actions com 10 workers)
  2. Carrega known_ids.txt (snapshot anterior)
  3. Identifica novos: corretorId presente hoje, ausente ontem, situacao=Ativo
  4. Enriquece novos via CNPJ.ws + fallbacks
  5. Filtra UF=MG
  6. Se há novos MG, envia email com CSV anexo
  7. Salva known_ids.txt atualizado (será commitado pelo workflow)
"""
import csv
import gzip
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.scrape import scrape_all  # noqa: E402
from pipeline.enrich import enrich_many  # noqa: E402
from pipeline.notify import send_email  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
STATE = REPO / "state"
OUT = REPO / "output"
STATE.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

KNOWN_IDS = STATE / "known_ids.txt.gz"
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


def build_email_html(new_mg, run_date):
    rows = []
    for r in new_mg:
        email_link = f'<a href="mailto:{r.get("email","")}">{r.get("email","")}</a>' if r.get("email") else ""
        tel = r.get("telefone", "") or ""
        rows.append(
            f"<tr>"
            f"<td>{r.get('nome','').strip()}</td>"
            f"<td>{r.get('cpfCnpj','')}</td>"
            f"<td>{r.get('protocolo','')}</td>"
            f"<td>{r.get('municipio','')}</td>"
            f"<td>{tel}</td>"
            f"<td>{email_link}</td>"
            f"<td>{r.get('produtos','')[:50]}</td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif">
<h2>Novos corretores SUSEP — {UF_FILTER} — {run_date}</h2>
<p><strong>{len(new_mg)} novos corretores</strong> em {UF_FILTER} identificados desde o último scan.</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">
<thead style="background:#f0f0f0">
<tr><th>Nome</th><th>CNPJ</th><th>Protocolo</th><th>Município</th><th>Telefone</th><th>Email</th><th>Ramos</th></tr>
</thead>
<tbody>{rows_html}</tbody>
</table>
<p style="color:#666;font-size:12px;margin-top:20px">
CSV completo em anexo. Pipeline automático Synkra SUSEP-{UF_FILTER}.
</p>
</body></html>"""


def main():
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_date = datetime.now().strftime("%Y-%m-%d")
    log(f"=== Pipeline run {run_id} | UF={UF_FILTER} | dry_run={DRY_RUN} ===")

    log("Step 1/5: Scrape SUSEP")
    records, errors = scrape_all(workers=10, on_progress=log)
    if errors:
        log(f"WARN: {len(errors)} pages failed after retries")
    if len(records) < 100000:
        log(f"ABORT: only {len(records)} records returned (expected >150k). Likely partial scrape.")
        return 1

    log("Step 2/5: Load known ids")
    known = load_known_ids()
    log(f"  known_ids previous: {len(known):,}")

    today_active = [r for r in records if r.get("situacao") == "Ativo"]
    today_ids = set(r["corretorId"] for r in today_active)
    log(f"  active today: {len(today_active):,}")

    log("Step 3/5: Detect new ids")
    if not known:
        log("  FIRST RUN: no previous snapshot. Building baseline only.")
        new_records = []
    else:
        new_ids = today_ids - known
        new_records = [r for r in today_active if r["corretorId"] in new_ids]
    log(f"  new since last run: {len(new_records)}")

    log("Step 4/5: Enrich + filter UF")
    new_mg = []
    if new_records:
        # focus on PJ (CNPJ completo)
        pj_new = [r for r in new_records if "*" not in (r.get("cpfCnpj") or "")]
        log(f"  PJ to enrich: {len(pj_new)} (PF skipped: {len(new_records)-len(pj_new)})")
        enriched = enrich_many(pj_new, delay=4.0, on_log=log)
        new_mg = [r for r in enriched if (r.get("uf") or "").upper() == UF_FILTER]
        log(f"  enriched {len(enriched)} | UF={UF_FILTER}: {len(new_mg)}")

    log("Step 5/5: Notify + persist")
    if new_mg and not DRY_RUN:
        # write CSV
        csv_path = OUT / f"novos_{UF_FILTER}_{run_id}.csv"
        fieldnames = [
            "nome", "cpfCnpj", "protocolo", "municipio", "uf",
            "telefone", "email", "produtos", "razao_social",
            "porte_empresa", "opcao_mei", "socio_principal",
            "cep", "logradouro", "numero", "bairro",
            "data_inicio_atividade", "situacao_cadastral", "fonte_enriq",
        ]
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for r in new_mg:
                r2 = {k: r.get(k, "") for k in fieldnames}
                if r2.get("nome"):
                    r2["nome"] = r2["nome"].strip()
                w.writerow(r2)

        subject = f"[SUSEP {UF_FILTER}] {len(new_mg)} novos corretores — {run_date}"
        body = (
            f"{len(new_mg)} novos corretores em {UF_FILTER} desde o último scan.\n\n"
            "Detalhes no HTML abaixo e no CSV em anexo.\n\n"
            f"Total escaneado hoje: {len(records):,}\n"
            f"Ativos hoje: {len(today_active):,}\n"
            f"Novos desde último scan: {len(new_records)}\n"
            f"-- Pipeline Synkra SUSEP\n"
        )
        html = build_email_html(new_mg, run_date)
        try:
            n = send_email(subject, body, attachments=[csv_path], html=html)
            log(f"  email sent to {n} recipient(s)")
        except Exception as e:
            log(f"  EMAIL FAILED: {type(e).__name__}: {e}")
    elif new_mg and DRY_RUN:
        log(f"  DRY_RUN — would have emailed {len(new_mg)} new {UF_FILTER}")
    else:
        log(f"  no new {UF_FILTER} — skipping email (per requirement)")

    save_known_ids(today_ids)
    LAST_RUN.write_text(json.dumps({
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "total_records": len(records),
        "active_today": len(today_active),
        "new_since_last": len(new_records),
        f"new_{UF_FILTER}": len(new_mg),
        "scrape_errors": len(errors),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"=== Pipeline done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
