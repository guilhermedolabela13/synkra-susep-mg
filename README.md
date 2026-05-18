# synkra-susep-mg

Pipeline diário automatizado que monitora a base pública de corretores da SUSEP, identifica novos cadastros, filtra por UF e envia email com os leads para a assessoria.

## O que faz

Todo dia às 06:30 BRT, o pipeline:

1. **Varre** a API pública SUSEP de corretores (~163.000 registros, 5-15 min)
2. **Compara** com o snapshot do dia anterior (estado persistido em `state/known_ids.txt.gz`)
3. **Identifica** novos `corretorId` ativos desde o último scan
4. **Enriquece** cada novo via CNPJ.ws + BrasilAPI + ReceitaWS (fallback em cascata)
5. **Filtra** UF configurada (padrão: `MG`)
6. **Envia email** com CSV anexo — *apenas se houver novos na UF*
7. **Commita** o snapshot atualizado para o próximo dia

## Setup

### 1. Criar o repo no GitHub

Crie um repositório **privado** (idealmente) e faça push deste código.

### 2. Configurar Gmail App Password

Pra que o pipeline envie email pela sua conta Gmail:

1. Habilite **2FA** na conta Gmail (obrigatório pra App Password)
2. Acesse https://myaccount.google.com/apppasswords
3. Crie uma App Password chamada "synkra-susep"
4. Copie a senha de 16 caracteres gerada

### 3. Adicionar Secrets ao GitHub

No repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret      | Valor                                        |
|-------------|----------------------------------------------|
| `SMTP_USER` | seu Gmail (ex.: `guilherme.dolabela13@gmail.com`) |
| `SMTP_PASS` | a App Password de 16 caracteres              |
| `SMTP_TO`   | destinatário(s), vírgula-separados           |

### 4. Habilitar permissão de commit

**Settings → Actions → General → Workflow permissions**: marcar **Read and write permissions**.

### 5. Primeiro run (baseline)

O primeiro run **não envia email** — ele só constrói a baseline (`state/known_ids.txt.gz`). A partir do segundo run, qualquer ID novo gera email.

Trigger manual: **Actions → Daily SUSEP scan → Run workflow**.

## Configuração

- **UF**: alterar `UF_FILTER` no workflow ou via input manual (`workflow_dispatch`).
- **Horário**: editar o `cron` em `.github/workflows/daily.yml`. Padrão: 09:30 UTC (06:30 BRT).
- **Dry run**: trigger manual com `dry_run=true` enriquece e roda tudo, mas não manda email.

## Estrutura

```
.github/workflows/
  daily.yml             # cron diário
pipeline/
  scrape.py             # scraper SUSEP
  enrich.py             # CNPJ.ws + BrasilAPI + ReceitaWS
  notify.py             # SMTP Gmail
  main.py               # orquestrador
state/
  known_ids.txt.gz      # snapshot anterior (commitado)
  last_run.json         # metadados do último run
output/                 # CSVs gerados (artifact da Action)
requirements.txt
```

## Limites e observações

- **Free tier GitHub Actions**: 2.000 min/mês. Cada run usa ~15 min. Cabe folgado.
- **Rate limit das APIs de CNPJ**: o enriquecimento é sequencial com delay de 4s entre chamadas. Como tipicamente há ~5-30 novos por dia, isso leva 1-2 min e raramente bate em rate limit.
- **PF (CPF mascarado)**: ignorados nesta versão. Hoje 100% dos novos de 2026 são PJ.
- **Filtro UF baseado em CNPJ**: a UF vem do endereço do estabelecimento na Receita Federal, não da SUSEP (que não publica UF).
- **LGPD**: dados públicos sob base legal de legítimo interesse (art. 7º IX). Manter LIA documentado e opt-out claro em todo outreach.
