from __future__ import annotations

import html
from datetime import UTC, datetime

from .models import Listing


def _money(value: float | None) -> str:
    if value is None:
        return "desconhecido"
    return f"{value:,.0f} €".replace(",", " ")


def _published_age(value: str | None) -> str:
    if not value:
        return "não indicado pelo portal"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        hours = max(0, int((datetime.now(UTC) - moment).total_seconds() // 3600))
        if hours < 1:
            return "há menos de uma hora"
        if hours < 48:
            return f"há cerca de {hours} h"
        return f"há cerca de {hours // 24} dias"
    except ValueError:
        return value


def format_alert(listing: Listing) -> str:
    event = {
        "new": "🆕 Novo anúncio",
        "republication": "♻️ Possível republicação",
        "price_drop": "📉 Descida de preço",
    }.get(listing.event, "🏠 Anúncio")
    lines = [f"<b>{event}</b>"]
    lines.append(f"<b>{html.escape(listing.title[:180])}</b>")
    area = f"{listing.area_m2:g} m²" if listing.area_m2 else "área desconhecida"
    lines.append(f"💶 {_money(listing.price)} · {listing.typology or '?'} · {area}")
    if listing.previous_price and listing.price and listing.previous_price != listing.price:
        lines.append(f"Preço anterior: <s>{_money(listing.previous_price)}</s>")
    if listing.price_per_m2:
        comparison = ""
        if listing.local_median_price_per_m2:
            comparison = f" · mediana da amostra {listing.local_median_price_per_m2:.2f} €/m²"
        lines.append(f"📐 {listing.price_per_m2:.2f} €/m²{comparison}")
    lines.append(f"📍 {html.escape(listing.location or 'localização incompleta')}")
    if listing.peak_drive_minutes is None:
        lines.append("🚗 Percurso até ao ISCAP: não foi possível estimar")
    else:
        lines.append(
            f"🚗 ~{listing.peak_drive_minutes} min até ao ISCAP em hora de ponta "
            f"({html.escape(listing.drive_estimate_kind or 'estimativa')})"
        )
    if listing.parking is True:
        parking = "confirmado no anúncio"
    elif listing.parking is False:
        parking = "o anúncio indica que não existe"
    else:
        parking = "por confirmar"
    lines.append(f"🅿️ Estacionamento: {parking}")
    if listing.published_at:
        lines.append(f"🕒 Publicado: {_published_age(listing.published_at)}")
    else:
        lines.append(f"🕒 Detetado pelo sistema: {_published_age(listing.first_seen_at)}")

    terms: list[str] = []
    if listing.terms.deposits is not None:
        terms.append(f"{listing.terms.deposits} caução(ões)")
    if listing.terms.deposit_amount is not None:
        terms.append(f"caução {_money(listing.terms.deposit_amount)}")
    if listing.terms.advance_rents is not None:
        terms.append(f"{listing.terms.advance_rents} renda(s) adiantada(s)")
    if listing.terms.entry_total is not None:
        terms.append(f"entrada {_money(listing.terms.entry_total)}")
    if terms:
        lines.append("🔑 " + " · ".join(terms))

    documents: list[str] = []
    if listing.terms.guarantor is True:
        documents.append("fiador")
    elif listing.terms.guarantor is False:
        documents.append("sem fiador")
    if listing.terms.payslips is True:
        documents.append("recibos de vencimento")
    if listing.terms.tax_return is True:
        documents.append("IRS")
    if listing.terms.work_contract is True:
        documents.append("contrato de trabalho")
    documents.extend(listing.terms.other_documents)
    if documents:
        lines.append("📄 " + " · ".join(html.escape(item) for item in documents))

    conditions: list[str] = []
    if listing.terms.minimum_contract_months is not None:
        conditions.append(f"contrato mínimo {listing.terms.minimum_contract_months} meses")
    if listing.terms.equipped_kitchen is True:
        conditions.append("cozinha equipada")
    elif listing.terms.equipped_kitchen is False:
        conditions.append("cozinha não equipada")
    if listing.terms.pets_allowed is True:
        conditions.append("animais permitidos")
    elif listing.terms.pets_allowed is False:
        conditions.append("animais não permitidos")
    if conditions:
        lines.append("🏡 " + " · ".join(conditions))
    if listing.terms.included_expenses:
        lines.append("🧾 Incluído: " + ", ".join(html.escape(item) for item in listing.terms.included_expenses))

    if listing.fraud_flags:
        lines.append("\n<b>⚠️ Verificar</b>")
        lines.extend(f"• {html.escape(flag)}" for flag in listing.fraud_flags)
    if listing.missing:
        lines.append("\n<b>Informação em falta</b>")
        lines.append("• " + html.escape(", ".join(listing.missing[:8])))

    lines.append(f'\n<a href="{html.escape(listing.url, quote=True)}">Abrir anúncio em {html.escape(listing.source)}</a>')
    return "\n".join(lines)[:4050]

