from pathlib import Path

from olha_casa.config import load_config
from olha_casa.telegram import TelegramSender


CONFIG = load_config(Path(__file__).parents[1] / "config.example.yml")


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "chat": {
                            "id": -100123456,
                            "type": "supergroup",
                            "title": "Alertas Casinhas",
                        }
                    },
                }
            ],
        }


def test_discovers_group_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr("olha_casa.telegram.requests.get", lambda *args, **kwargs: FakeResponse())

    sender = TelegramSender(CONFIG)
    sender.validate()

    assert sender.chat_id == "-100123456"

