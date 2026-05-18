"""Envio de email com lista de novos corretores MG."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path


def send_email(subject, body, attachments=None, html=None):
    """Envia email via Gmail SMTP. Variáveis de ambiente esperadas:
       SMTP_USER, SMTP_PASS, SMTP_TO."""
    user = os.environ["SMTP_USER"]
    pwd = os.environ["SMTP_PASS"]
    to_raw = os.environ.get("SMTP_TO", user)
    to_addrs = [a.strip() for a in to_raw.split(",") if a.strip()]

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    for path in attachments or []:
        p = Path(path)
        if not p.exists():
            continue
        with open(p, "rb") as f:
            data = f.read()
        msg.add_attachment(
            data, maintype="application", subtype="octet-stream", filename=p.name
        )

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(user, pwd)
        srv.send_message(msg)
    return len(to_addrs)
