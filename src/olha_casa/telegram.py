from __future__ import annotations

import os

import requests


class TelegramSender:
    def __init__(self, config: dict, force_dry_run: bool = False):
        telegram = config["telegram"]
        self.token = os.getenv(telegram.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
        self.chat_id = os.getenv(telegram.get("chat_id_env", "TELEGRAM_CHAT_ID"))
        dry_env = os.getenv(telegram.get("dry_run_env", "OLHA_CASA_DRY_RUN"), "")
        self.dry_run = force_dry_run or dry_env.lower() in {"1", "true", "yes", "sim"}

    def validate(self) -> None:
        if self.dry_run:
            return
        if not self.token or not self.chat_id:
            raise RuntimeError(
                "Faltam TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID. "
                "Defina-os como GitHub Actions Secrets."
            )

    def send(self, message: str) -> None:
        if self.dry_run:
            print("\n--- ALERTA TELEGRAM (simulação) ---\n" + message + "\n")
            return
        response = requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        response.raise_for_status()

