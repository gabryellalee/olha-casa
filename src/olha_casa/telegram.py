from __future__ import annotations

import os
import sys
import unicodedata

import requests


class TelegramSender:
    def __init__(self, config: dict, force_dry_run: bool = False):
        telegram = config["telegram"]
        self.token = os.getenv(telegram.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
        self.chat_id = os.getenv(telegram.get("chat_id_env", "TELEGRAM_CHAT_ID"))
        self.group_title = telegram.get("group_title", "Alertas Casinhas")
        dry_env = os.getenv(telegram.get("dry_run_env", "OLHA_CASA_DRY_RUN"), "")
        self.dry_run = force_dry_run or dry_env.lower() in {"1", "true", "yes", "sim"}

    def validate(self) -> None:
        if self.dry_run:
            return
        if not self.token:
            raise RuntimeError(
                "Falta TELEGRAM_BOT_TOKEN. Defina-o como GitHub Actions Secret."
            )
        if not self.chat_id:
            self.chat_id = self._discover_chat_id()

    @staticmethod
    def _normalized(value: str) -> str:
        return "".join(
            character
            for character in unicodedata.normalize("NFKD", value.casefold())
            if not unicodedata.combining(character)
        ).strip()

    def _discover_chat_id(self) -> str:
        response = requests.get(
            f"https://api.telegram.org/bot{self.token}/getUpdates",
            params={"limit": 100, "timeout": 0},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError("O Telegram recusou a leitura das mensagens recentes do bot.")

        groups: list[dict] = []
        for update in reversed(payload.get("result", [])):
            container = (
                update.get("message")
                or update.get("channel_post")
                or update.get("my_chat_member")
                or update.get("chat_member")
                or {}
            )
            chat = container.get("chat") or {}
            if chat.get("type") in {"group", "supergroup"} and chat.get("id"):
                groups.append(chat)

        target = self._normalized(str(self.group_title or ""))
        for chat in groups:
            if self._normalized(str(chat.get("title") or "")) == target:
                return str(chat["id"])
        unique_ids = {str(chat["id"]) for chat in groups}
        if len(unique_ids) == 1:
            return unique_ids.pop()
        raise RuntimeError(
            f"Não encontrei o grupo {self.group_title!r}. Envie primeiro uma mensagem "
            "no grupo com o bot presente ou defina TELEGRAM_CHAT_ID nos Secrets."
        )

    def send(self, message: str) -> None:
        if self.dry_run:
            output = "\n--- ALERTA TELEGRAM (simulação) ---\n" + message + "\n"
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            safe_output = output.encode(encoding, errors="backslashreplace").decode(encoding)
            print(safe_output)
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
