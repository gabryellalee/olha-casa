"""Lista os chats que contactaram o bot, sem mostrar o token."""

from __future__ import annotations

import os
import sys

import requests


token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token:
    sys.exit("Defina primeiro a variável TELEGRAM_BOT_TOKEN.")

response = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
response.raise_for_status()
seen = set()
for update in response.json().get("result", []):
    message = update.get("message") or update.get("channel_post") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None or chat_id in seen:
        continue
    seen.add(chat_id)
    name = chat.get("title") or chat.get("username") or chat.get("first_name") or "sem nome"
    print(f"{name}: {chat_id}")

if not seen:
    print("Nenhum chat encontrado. Envie uma mensagem no grupo e volte a executar.")

