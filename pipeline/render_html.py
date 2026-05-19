"""
Renderiza HTML interativo auto-contido (sem CDN) com filtros e botões de contato.
Usado pelo pipeline para gerar o anexo do email.
"""
import html
import json
from datetime import datetime
from pathlib import Path


PROTO_YEAR_MAP = {
    "201": 2010, "202": 2020, "212": 2021, "222": 2022,
    "232": 2023, "242": 2024, "252": 2025, "262": 2026,
}


def normalize_phone_for_wa(tel):
    digits = "".join(c for c in (tel or "") if c.isdigit())
    if not digits:
        return ""
    if not digits.startswith("55"):
        digits = "55" + digits
    return digits


def format_phone(tel):
    digits = "".join(c for c in (tel or "") if c.isdigit())
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return tel or ""


def is_placeholder_phone(tel):
    digits = "".join(c for c in (tel or "") if c.isdigit())
    if not digits:
        return True
    body = digits[2:] if digits.startswith("55") else digits
    body = body[2:]
    if not body:
        return True
    if len(set(body)) == 1:
        return True
    return False


def year_from_protocolo(p):
    if not p or len(p) < 3:
        return None
    return PROTO_YEAR_MAP.get(p[:3])


def prepare_rows(records):
    out = []
    for r in records:
        tel = (r.get("telefone") or "").strip()
        data_abert = r.get("data_inicio_atividade", "")
        try:
            data_fmt = datetime.strptime(data_abert, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            data_fmt = data_abert
        proto = r.get("protocolo", "") or ""
        ano_susep = year_from_protocolo(proto)
        detected = r.get("detected_at", "") or ""
        try:
            detected_fmt = datetime.strptime(detected, "%Y-%m-%d").strftime("%d/%m/%Y") if detected else ""
        except Exception:
            detected_fmt = detected
        out.append({
            "nome": (r.get("nome") or "").strip(),
            "razao_social": r.get("razao_social", "") or "",
            "cnpj": r.get("cpfCnpj", "") or r.get("cnpj", "") or "",
            "protocolo": proto,
            "susep_ano": str(ano_susep) if ano_susep else "",
            "municipio": (r.get("municipio") or "").title(),
            "uf": r.get("uf", "") or "",
            "telefone": format_phone(tel),
            "telefone_wa": normalize_phone_for_wa(tel),
            "telefone_valido": not is_placeholder_phone(tel),
            "email": (r.get("email") or "").strip(),
            "data_inicio_atividade": data_fmt,
            "detected_at": detected_fmt,
            "produtos": r.get("produtos", "") or "",
            "porte_empresa": r.get("porte_empresa", "") or "",
            "opcao_mei": r.get("opcao_mei", "") or "",
            "socio_principal": (r.get("socio_principal") or "").title(),
            "bairro": (r.get("bairro") or "").title(),
            "logradouro": (r.get("logradouro") or "").strip(),
            "numero": r.get("numero", "") or "",
            "cep": r.get("cep", "") or "",
        })
    return out


def render(records, output_path, uf_filter="MG", title_extra=""):
    rows = prepare_rows(records)
    rows.sort(key=lambda r: r["detected_at"] or r["data_inicio_atividade"], reverse=True)

    total = len(rows)
    com_email = sum(1 for r in rows if r["email"])
    com_tel = sum(1 for r in rows if r["telefone_valido"])
    com_ambos = sum(1 for r in rows if r["email"] and r["telefone_valido"])
    municipios = sorted({r["municipio"] for r in rows if r["municipio"]})
    portes = sorted({r["porte_empresa"] for r in rows if r["porte_empresa"]})

    data_scan = datetime.now().strftime("%d/%m/%Y às %H:%M")
    data_dia = datetime.now().strftime("%d/%m/%Y")

    subtitle = f"Snapshot {data_scan} · {total} corretores {uf_filter}"
    if title_extra:
        subtitle += f" · {title_extra}"

    data_json = json.dumps(rows, ensure_ascii=False)

    html_doc = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Novos corretores {uf_filter} · {data_dia}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0f1115;color:#e6e8eb;line-height:1.5;min-height:100vh}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}
header{{background:linear-gradient(135deg,#1a1d24 0%,#252932 100%);padding:32px;border-radius:16px;margin-bottom:24px;border:1px solid #2a2e38}}
h1{{font-size:24px;font-weight:600;margin-bottom:8px;letter-spacing:-0.02em}}
.subtitle{{color:#8a93a6;font-size:14px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:24px}}
.kpi{{background:#0f1115;padding:16px;border-radius:10px;border:1px solid #2a2e38}}
.kpi-label{{color:#8a93a6;font-size:11px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px}}
.kpi-value{{font-size:28px;font-weight:700;color:#e6e8eb}}
.kpi-value.green{{color:#4ade80}}
.kpi-value.blue{{color:#60a5fa}}
.kpi-value.gold{{color:#fbbf24}}
.filters{{background:#1a1d24;padding:20px;border-radius:12px;margin-bottom:20px;border:1px solid #2a2e38;display:grid;grid-template-columns:1fr auto auto auto auto auto;gap:12px;align-items:center}}
.filters input,.filters select{{background:#0f1115;border:1px solid #2a2e38;color:#e6e8eb;padding:10px 14px;border-radius:8px;font-size:14px;font-family:inherit;outline:none;transition:border-color 0.15s}}
.filters input:focus,.filters select:focus{{border-color:#60a5fa}}
.filters input{{width:100%}}
.toggle{{display:flex;align-items:center;gap:6px;color:#8a93a6;font-size:13px;user-select:none;cursor:pointer;padding:8px 12px;border-radius:8px;background:#0f1115;border:1px solid #2a2e38;transition:background 0.15s}}
.toggle:hover{{background:#161922}}
.toggle.active{{background:#1e293b;border-color:#3b82f6;color:#bfdbfe}}
.toggle input{{accent-color:#3b82f6;cursor:pointer}}
.export-btn{{background:#3b82f6;color:white;border:none;padding:10px 18px;border-radius:8px;cursor:pointer;font-weight:500;font-size:14px;transition:background 0.15s}}
.export-btn:hover{{background:#2563eb}}
.results-info{{color:#8a93a6;font-size:13px;margin-bottom:12px;padding:0 4px}}
.table-wrap{{background:#1a1d24;border-radius:12px;border:1px solid #2a2e38;overflow:hidden}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#161922;color:#8a93a6;text-align:left;padding:14px 12px;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:0.05em;border-bottom:1px solid #2a2e38;cursor:pointer;user-select:none;white-space:nowrap}}
th:hover{{color:#e6e8eb}}
th.sorted-asc::after{{content:" ↑";color:#60a5fa}}
th.sorted-desc::after{{content:" ↓";color:#60a5fa}}
td{{padding:14px 12px;border-bottom:1px solid #22262f;vertical-align:top}}
tr:hover{{background:#1e2229}}
.nome{{font-weight:600;color:#e6e8eb;max-width:280px;line-height:1.35}}
.nome-sub{{color:#8a93a6;font-size:11px;font-weight:400;margin-top:3px}}
.cidade{{color:#bfdbfe;white-space:nowrap}}
.data{{color:#8a93a6;font-size:12px;white-space:nowrap}}
.contact-btn{{display:inline-flex;align-items:center;gap:5px;padding:5px 10px;border-radius:6px;font-size:12px;text-decoration:none;border:1px solid transparent;cursor:pointer;font-family:inherit;background:none;transition:all 0.15s;margin:1px 2px 1px 0}}
.btn-wa{{background:#10b981;color:white}}
.btn-wa:hover{{background:#059669}}
.btn-mail{{background:#3b82f6;color:white}}
.btn-mail:hover{{background:#2563eb}}
.btn-copy{{background:#374151;color:#d1d5db;border-color:#4b5563}}
.btn-copy:hover{{background:#4b5563;color:white}}
.btn-tel{{background:#1f2937;color:#9ca3af;border-color:#374151;font-family:ui-monospace,monospace}}
.btn-tel:hover{{background:#374151;color:white}}
.no-contact{{color:#4b5563;font-style:italic;font-size:11px}}
.placeholder{{color:#dc2626;font-size:10px;margin-left:4px}}
.tag{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;background:#374151;color:#d1d5db;margin-left:4px;font-weight:500}}
.tag-mei{{background:#7c2d12;color:#fed7aa}}
.tag-susep{{background:#1e3a8a;color:#bfdbfe;font-family:ui-monospace,monospace}}
.tag-susep-hot{{background:#7c2d12;color:#fed7aa}}
.tag-fresh{{background:#14532d;color:#86efac}}
.tag-baseline{{background:#374151;color:#9ca3af;font-style:italic}}
.produtos{{color:#8a93a6;font-size:11px;max-width:200px}}
.cnpj{{color:#8a93a6;font-family:ui-monospace,monospace;font-size:11px;white-space:nowrap}}
footer{{margin-top:32px;padding:20px;color:#4b5563;font-size:12px;text-align:center}}
.empty{{text-align:center;padding:60px 20px;color:#4b5563}}
.empty-icon{{font-size:48px;margin-bottom:16px}}
.toast{{position:fixed;bottom:24px;right:24px;background:#10b981;color:white;padding:14px 22px;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.4);transform:translateY(120%);transition:transform 0.3s;font-weight:500;font-size:14px}}
.toast.show{{transform:translateY(0)}}
@media(max-width:768px){{
.filters{{grid-template-columns:1fr;gap:8px}}
.kpis{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>Novos corretores {uf_filter} — SUSEP</h1>
  <div class="subtitle">{html.escape(subtitle)}</div>
  <div class="kpis">
    <div class="kpi"><div class="kpi-label">Total</div><div class="kpi-value">{total}</div></div>
    <div class="kpi"><div class="kpi-label">Com email</div><div class="kpi-value blue">{com_email}</div></div>
    <div class="kpi"><div class="kpi-label">Com telefone</div><div class="kpi-value green">{com_tel}</div></div>
    <div class="kpi"><div class="kpi-label">Email + telefone</div><div class="kpi-value gold">{com_ambos}</div></div>
  </div>
</header>

<div class="filters">
  <input type="text" id="search" placeholder="🔎 Buscar por nome, CNPJ, sócio, bairro, endereço…">
  <select id="filter-cidade">
    <option value="">Todas as cidades</option>
    {''.join(f'<option value="{html.escape(m)}">{html.escape(m)}</option>' for m in municipios)}
  </select>
  <select id="filter-porte">
    <option value="">Todos os portes</option>
    {''.join(f'<option value="{html.escape(p)}">{html.escape(p)}</option>' for p in portes)}
  </select>
  <select id="filter-susep">
    <option value="">Registro SUSEP: todos</option>
    <option value="2026">2026 (mais frescos)</option>
    <option value="2025">2025</option>
    <option value="2024">2024</option>
    <option value="2023">2023 e anteriores</option>
  </select>
  <label class="toggle" id="toggle-email-label">
    <input type="checkbox" id="filter-email"> Só com email
  </label>
  <label class="toggle" id="toggle-tel-label">
    <input type="checkbox" id="filter-tel"> Só com telefone válido
  </label>
</div>

<div class="results-info" id="results-info"></div>

<div class="table-wrap">
<table id="tabela">
<thead>
<tr>
  <th data-sort="nome">Nome / CNPJ</th>
  <th data-sort="municipio">Cidade</th>
  <th data-sort="detected_at">Detectado em</th>
  <th data-sort="susep_ano">Registro SUSEP</th>
  <th data-sort="data_inicio_atividade">CNPJ aberto em</th>
  <th data-sort="porte_empresa">Porte</th>
  <th>Contato</th>
  <th data-sort="produtos">Ramos</th>
</tr>
</thead>
<tbody id="tbody"></tbody>
</table>
</div>

<div id="empty-state" class="empty" style="display:none">
  <div class="empty-icon">🔍</div>
  <div>Nenhum corretor encontrado com esses filtros.</div>
</div>

<footer>
  <button class="export-btn" id="export-csv">📥 Exportar visíveis em CSV</button>
  &nbsp;&nbsp;
  Pipeline automático Synkra · base pública SUSEP · enriquecimento Receita Federal
</footer>
</div>

<div class="toast" id="toast"></div>

<script>
const DATA = {data_json};
let filteredData = [...DATA];
let sortField = 'detected_at';
let sortDir = 'desc';

const tbody = document.getElementById('tbody');
const search = document.getElementById('search');
const fCidade = document.getElementById('filter-cidade');
const fPorte = document.getElementById('filter-porte');
const fSusep = document.getElementById('filter-susep');
const fEmail = document.getElementById('filter-email');
const fTel = document.getElementById('filter-tel');
const labelEmail = document.getElementById('toggle-email-label');
const labelTel = document.getElementById('toggle-tel-label');
const resultsInfo = document.getElementById('results-info');
const emptyState = document.getElementById('empty-state');

function escapeHtml(s) {{
  if (!s) return '';
  return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}

function toast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 1800);
}}

function copy(text) {{
  navigator.clipboard.writeText(text).then(() => toast('Copiado: ' + text));
}}

function render() {{
  if (filteredData.length === 0) {{
    tbody.innerHTML = '';
    emptyState.style.display = 'block';
    resultsInfo.textContent = '';
    return;
  }}
  emptyState.style.display = 'none';
  resultsInfo.textContent = `Mostrando ${{filteredData.length}} de ${{DATA.length}} corretores`;

  tbody.innerHTML = filteredData.map(r => {{
    const tel = r.telefone || '';
    const telWa = r.telefone_wa || '';
    const telValido = r.telefone_valido;
    const email = r.email || '';
    const meiTag = r.opcao_mei === 'S' ? '<span class="tag tag-mei">MEI</span>' : '';
    let susepTag = '';
    if (r.susep_ano === '2026') {{
      susepTag = `<span class="tag tag-susep-hot">SUSEP ${{r.susep_ano}}</span>`;
    }} else if (r.susep_ano) {{
      susepTag = `<span class="tag tag-susep">SUSEP ${{r.susep_ano}}</span>`;
    }}
    let detectedHtml = r.detected_at
      ? `<span class="tag tag-fresh">${{escapeHtml(r.detected_at)}}</span>`
      : `<span class="tag tag-baseline">Pré-baseline</span>`;

    let contatoHtml = '';
    if (telValido && tel) {{
      contatoHtml += `<a class="contact-btn btn-wa" href="https://wa.me/${{telWa}}" target="_blank" title="Abrir WhatsApp">💬 WhatsApp</a>`;
      contatoHtml += `<button class="contact-btn btn-tel" onclick="copy('${{tel}}')" title="Copiar telefone">${{tel}}</button>`;
    }} else if (tel) {{
      contatoHtml += `<span class="contact-btn btn-tel" style="opacity:0.5">${{tel}}<span class="placeholder">⚠ inválido</span></span>`;
    }}
    if (email) {{
      contatoHtml += `<a class="contact-btn btn-mail" href="mailto:${{email}}" title="Enviar email">✉ Email</a>`;
      contatoHtml += `<button class="contact-btn btn-copy" onclick="copy('${{email}}')" title="Copiar email">📋</button>`;
    }}
    if (!contatoHtml) {{
      contatoHtml = '<span class="no-contact">Sem contato cadastrado</span>';
    }}

    const endereco = [r.logradouro, r.numero, r.bairro].filter(Boolean).join(', ');
    const socio = r.socio_principal ? `<div class="nome-sub">Sócio: ${{escapeHtml(r.socio_principal)}}</div>` : '';
    const enderecoLine = endereco ? `<div class="nome-sub">${{escapeHtml(endereco)}}</div>` : '';

    return `<tr>
      <td class="nome">${{escapeHtml(r.nome)}}${{meiTag}}
        <div class="nome-sub cnpj">CNPJ: ${{r.cnpj}}</div>
        ${{socio}}
        ${{enderecoLine}}
      </td>
      <td class="cidade">${{escapeHtml(r.municipio)}}<div class="nome-sub">${{r.cep}}</div></td>
      <td>${{detectedHtml}}</td>
      <td>${{susepTag}}<div class="nome-sub cnpj">proto: ${{r.protocolo}}</div></td>
      <td class="data">${{escapeHtml(r.data_inicio_atividade)}}</td>
      <td class="data">${{escapeHtml(r.porte_empresa)}}</td>
      <td>${{contatoHtml}}</td>
      <td class="produtos">${{escapeHtml(r.produtos)}}</td>
    </tr>`;
  }}).join('');
}}

function applyFilters() {{
  const q = search.value.trim().toLowerCase();
  const cidade = fCidade.value;
  const porte = fPorte.value;
  const onlyEmail = fEmail.checked;
  const onlyTel = fTel.checked;
  const susepYear = fSusep.value;

  labelEmail.classList.toggle('active', onlyEmail);
  labelTel.classList.toggle('active', onlyTel);

  filteredData = DATA.filter(r => {{
    if (cidade && r.municipio !== cidade) return false;
    if (porte && r.porte_empresa !== porte) return false;
    if (susepYear) {{
      if (susepYear === '2023') {{
        if (!r.susep_ano || parseInt(r.susep_ano) > 2023) return false;
      }} else if (r.susep_ano !== susepYear) return false;
    }}
    if (onlyEmail && !r.email) return false;
    if (onlyTel && !r.telefone_valido) return false;
    if (q) {{
      const hay = [
        r.nome, r.cnpj, r.socio_principal, r.bairro, r.municipio,
        r.email, r.telefone, r.razao_social, r.logradouro, r.produtos
      ].join(' ').toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});

  applySort();
  render();
}}

function applySort() {{
  filteredData.sort((a, b) => {{
    const va = (a[sortField] || '').toString().toLowerCase();
    const vb = (b[sortField] || '').toString().toLowerCase();
    if (va < vb) return sortDir === 'asc' ? -1 : 1;
    if (va > vb) return sortDir === 'asc' ? 1 : -1;
    return 0;
  }});
}}

document.querySelectorAll('th[data-sort]').forEach(th => {{
  th.addEventListener('click', () => {{
    const field = th.dataset.sort;
    if (sortField === field) {{
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    }} else {{
      sortField = field;
      sortDir = 'asc';
    }}
    document.querySelectorAll('th').forEach(t => {{ t.classList.remove('sorted-asc','sorted-desc'); }});
    th.classList.add(sortDir === 'asc' ? 'sorted-asc' : 'sorted-desc');
    applySort();
    render();
  }});
}});

search.addEventListener('input', applyFilters);
fCidade.addEventListener('change', applyFilters);
fPorte.addEventListener('change', applyFilters);
fSusep.addEventListener('change', applyFilters);
fEmail.addEventListener('change', applyFilters);
fTel.addEventListener('change', applyFilters);

document.getElementById('export-csv').addEventListener('click', () => {{
  const headers = ['nome','cnpj','protocolo','susep_ano','detected_at','municipio','data_inicio_atividade','porte_empresa','telefone','email','socio_principal','bairro','logradouro','numero','cep','produtos'];
  const lines = [headers.join(',')];
  filteredData.forEach(r => {{
    lines.push(headers.map(h => {{
      const v = (r[h] || '').toString().replace(/"/g, '""');
      return /[,;"\\n]/.test(v) ? `"${{v}}"` : v;
    }}).join(','));
  }});
  const blob = new Blob(['\\uFEFF' + lines.join('\\n')], {{type: 'text/csv;charset=utf-8'}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `corretores_filtrados_${{new Date().toISOString().slice(0,10)}}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  toast(`${{filteredData.length}} linhas exportadas`);
}});

document.querySelector('th[data-sort="detected_at"]').classList.add('sorted-desc');
applyFilters();
</script>
</body>
</html>"""

    Path(output_path).write_text(html_doc, encoding="utf-8")
    return len(html_doc)
