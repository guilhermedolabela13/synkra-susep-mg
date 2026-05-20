"""
Enriquece registros SUSEP via 3 APIs com fallback:
  1. CNPJ.ws    (publica.cnpj.ws)        — email + telefone + UF
  2. BrasilAPI  (brasilapi.com.br)       — UF + telefone (email às vezes)
  3. ReceitaWS  (receitaws.com.br)       — email + UF + telefone

Modo single-thread com delay configurável (recomendado quando poucos itens).
"""
import time
from datetime import datetime

import requests


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    return s


# ----- CNPJ.ws -----

def fetch_cnpjws(cnpj, s):
    try:
        r = s.get(f"https://publica.cnpj.ws/cnpj/{cnpj}", timeout=20)
        if r.status_code == 429:
            return "rl"
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def normalize_cnpjws(d):
    est = d.get("estabelecimento") or {}
    estado = est.get("estado") or {}
    cidade = est.get("cidade") or {}
    socios = d.get("socios") or []
    porte = d.get("porte") or {}
    simples = d.get("simples") or {}
    tel = f"({est.get('ddd1') or ''}) {est.get('telefone1') or ''}" if est.get("telefone1") else ""
    tipo_log = est.get("tipo_logradouro") or ""
    logradouro = est.get("logradouro") or ""
    return {
        "uf": estado.get("sigla") or "",
        "municipio": cidade.get("nome") or "",
        "cep": est.get("cep") or "",
        "logradouro": (tipo_log + " " + logradouro).strip(),
        "numero": est.get("numero") or "",
        "bairro": est.get("bairro") or "",
        "email": (est.get("email") or "").lower(),
        "telefone": tel,
        "data_inicio_atividade": est.get("data_inicio_atividade") or "",
        "situacao_cadastral": est.get("situacao_cadastral") or "",
        "razao_social": d.get("razao_social") or "",
        "porte_empresa": porte.get("descricao") or "",
        "opcao_mei": "S" if simples.get("mei") == "Sim" else "N",
        "socio_principal": (socios[0].get("nome") or "") if socios else "",
        "fonte_enriq": "cnpjws",
    }


# ----- BrasilAPI -----

def fetch_brasilapi(cnpj, s):
    try:
        r = s.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", timeout=15)
        if r.status_code == 429:
            return "rl"
        if r.status_code in (404, 400):
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def normalize_brasilapi(d):
    tel_raw = d.get("ddd_telefone_1") or ""
    tel = f"({tel_raw[:2]}) {tel_raw[2:]}" if len(tel_raw) >= 10 else tel_raw
    socios = d.get("qsa") or []
    tipo_log = d.get("descricao_tipo_de_logradouro") or ""
    logradouro = d.get("logradouro") or ""
    return {
        "uf": d.get("uf") or "",
        "municipio": d.get("municipio") or "",
        "cep": d.get("cep") or "",
        "logradouro": (tipo_log + " " + logradouro).strip(),
        "numero": d.get("numero") or "",
        "bairro": d.get("bairro") or "",
        "email": (d.get("email") or "").lower(),
        "telefone": tel,
        "data_inicio_atividade": d.get("data_inicio_atividade") or "",
        "situacao_cadastral": d.get("descricao_situacao_cadastral") or "",
        "razao_social": d.get("razao_social") or "",
        "porte_empresa": d.get("porte") or "",
        "opcao_mei": "S" if d.get("opcao_pelo_mei") else "N",
        "socio_principal": (socios[0].get("nome_socio") or "") if socios else "",
        "fonte_enriq": "brasilapi",
    }


# ----- ReceitaWS -----

def fetch_receitaws(cnpj, s):
    try:
        r = s.get(f"https://receitaws.com.br/v1/cnpj/{cnpj}", timeout=15)
        if r.status_code == 429:
            return "rl"
        if r.status_code in (404, 400):
            return None
        r.raise_for_status()
        d = r.json()
        if d.get("status") == "ERROR":
            return None
        return d
    except Exception:
        return None


def normalize_receitaws(d):
    tel = (d.get("telefone") or "").split("/")[0].strip()
    socios = d.get("qsa") or []
    return {
        "uf": d.get("uf") or "",
        "municipio": d.get("municipio") or "",
        "cep": (d.get("cep") or "").replace(".", "").replace("-", ""),
        "logradouro": d.get("logradouro") or "",
        "numero": d.get("numero") or "",
        "bairro": d.get("bairro") or "",
        "email": (d.get("email") or "").lower(),
        "telefone": tel,
        "data_inicio_atividade": d.get("abertura") or "",
        "situacao_cadastral": d.get("situacao") or "",
        "razao_social": d.get("nome") or "",
        "porte_empresa": d.get("porte") or "",
        "opcao_mei": "",
        "socio_principal": (socios[0].get("nome") or "") if socios else "",
        "fonte_enriq": "receitaws",
    }


# ----- Orquestrador -----

def enrich_one(cnpj, session, on_log=None):
    """Tenta as 3 APIs em ordem. Retorna dict normalizado ou {}."""
    # CNPJ.ws (melhor email)
    d = fetch_cnpjws(cnpj, session)
    if d == "rl":
        time.sleep(8)
        d = fetch_cnpjws(cnpj, session)
        if d == "rl":
            d = None
    if isinstance(d, dict):
        return normalize_cnpjws(d)
    # BrasilAPI
    d = fetch_brasilapi(cnpj, session)
    if d == "rl":
        time.sleep(8)
        d = fetch_brasilapi(cnpj, session)
        if d == "rl":
            d = None
    if isinstance(d, dict):
        return normalize_brasilapi(d)
    # ReceitaWS (último, rate-limited)
    d = fetch_receitaws(cnpj, session)
    if d == "rl":
        time.sleep(22)
        d = fetch_receitaws(cnpj, session)
        if d == "rl":
            d = None
    if isinstance(d, dict):
        return normalize_receitaws(d)
    return {}


def enrich_many(records, delay=4.0, on_log=None):
    """Enriquece lista de records (cada um precisa ter cpfCnpj). Modifica in-place + retorna lista."""
    session = make_session()
    for i, rec in enumerate(records, 1):
        cnpj = rec.get("cpfCnpj") or rec.get("cnpj")
        if not cnpj or "*" in cnpj:
            rec["fonte_enriq"] = "skipped_pf"
            continue
        extra = enrich_one(cnpj, session, on_log=on_log)
        if extra:
            rec.update(extra)
        else:
            rec["fonte_enriq"] = "none"
        if on_log and (i % 10 == 0 or i == len(records)):
            on_log(f"  enrich {i}/{len(records)} | last={rec.get('uf','?')} {rec.get('fonte_enriq','')}")
        time.sleep(delay)
    return records
