from olha_casa.message import format_alert
from olha_casa.models import Listing


def test_alert_does_not_include_suggested_contact_message():
    listing = Listing(
        source="teste",
        source_id="1",
        url="https://example.test/1",
        title="Apartamento T2",
        price=700,
        typology="T2",
        location="Maia",
        missing=["área útil", "necessidade de fiador"],
    )

    message = format_alert(listing)

    assert "Mensagem pronta" not in message
    assert "Gostaríamos de agendar uma visita" not in message
    assert "Abrir anúncio" in message

