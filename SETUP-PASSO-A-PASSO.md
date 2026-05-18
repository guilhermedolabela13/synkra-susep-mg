# Setup passo-a-passo (~15 min)

## 1. Criar Gmail App Password (5 min)

1. Acesse https://myaccount.google.com — logue com `guilherme.dolabela13@gmail.com`
2. Vá em **Segurança** (menu lateral)
3. Confirme que **Verificação em duas etapas** está **ativada**. Se não, ative agora (Google guia o processo, leva 2 min).
4. Volte a **Segurança** e role até **Senhas de app**. Se não vir, acesse direto: https://myaccount.google.com/apppasswords
5. **Nome do app**: `synkra-susep` → **Criar**
6. **Copie a senha de 16 caracteres** que aparece (formato: `abcd efgh ijkl mnop` — sem os espaços quando colar).

## 2. Criar repositório GitHub (3 min)

1. Acesse https://github.com/new (se não tiver conta GitHub, crie em github.com/signup)
2. **Repository name**: `synkra-susep-mg`
3. Marque **Private**
4. Clique **Create repository**
5. Não adicione README/gitignore/license (já temos no projeto)

## 3. Subir os arquivos (2 min)

Abra o **Git Bash** ou **PowerShell** e rode (substitua `SEU_USUARIO` pelo seu user GitHub):

```bash
cd /c/Users/guegs/synkra-susep-mg
git init
git add .
git commit -m "feat: pipeline SUSEP-MG diário"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/synkra-susep-mg.git
git push -u origin main
```

GitHub vai pedir login — use seu usuário e um **Personal Access Token** como senha (Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new → marque `repo` → Generate → copie).

## 4. Configurar Secrets (3 min)

No repositório recém-criado:

1. **Settings → Secrets and variables → Actions**
2. **New repository secret** três vezes:

   | Name        | Valor                                          |
   |-------------|------------------------------------------------|
   | `SMTP_USER` | `guilherme.dolabela13@gmail.com`               |
   | `SMTP_PASS` | (cole a App Password de 16 caracteres)         |
   | `SMTP_TO`   | `guilherme.dolabela13@gmail.com`               |

## 5. Habilitar permissão de commit do bot (1 min)

**Settings → Actions → General**

- Role até **Workflow permissions**
- Marque **Read and write permissions**
- **Save**

## 6. Primeiro run manual — construir baseline (10 min)

1. Vá em **Actions** (aba superior do repo)
2. Pode aparecer um botão "I understand my workflows, go ahead and enable them" — clique.
3. Clique em **Daily SUSEP scan** (menu esquerdo)
4. **Run workflow** (botão à direita) → **dry_run: false** → **Run workflow**
5. Aguarde ~10-15 minutos. O run aparece na lista. Clique nele pra ver os logs em tempo real.
6. Esse run é o **baseline** — não vai enviar email porque ainda não há "anterior" pra comparar. Mas vai criar o `state/known_ids.txt.gz` no repo.

## 7. Próximos runs (automáticos)

A partir do dia seguinte, todo dia às **06:30 BRT** o pipeline roda sozinho. Se houver corretores novos em MG, você recebe email. Se não houver, silêncio.

## Mudanças comuns

- **Mudar UF**: edite `.github/workflows/daily.yml`, linha do input `default: "MG"`, ou rode manual via Run workflow.
- **Mudar horário**: edite o `cron` (formato UTC). Ex.: `0 12 * * *` = 09:00 BRT.
- **Adicionar destinatários**: edite o secret `SMTP_TO` com vírgulas — ex.: `voce@x.com,assessoria@y.com`.
- **Pausar o pipeline**: **Actions → Daily SUSEP scan → ... (três pontos) → Disable workflow**.

## Troubleshooting

- **Run falha em "send_email"** → App Password errado ou 2FA não ativado. Recrie o App Password e atualize o secret.
- **"only N records returned (expected >150k)"** → API SUSEP teve problema temporário. Rode manualmente de novo.
- **Email não chega** → veja a aba de spam, ou pode ter excedido limite Gmail (500 emails/dia — improvável).
