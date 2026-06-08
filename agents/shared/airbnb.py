"""Leitura do calendário de disponibilidade via iCal feed do Airbnb."""

import os
from datetime import date, timedelta

import requests
from icalendar import Calendar


def _fetch_calendar() -> Calendar:
    url = os.environ["AIRBNB_ICAL_URL"]
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return Calendar.from_ical(resp.content)


def get_booked_ranges() -> list[tuple[date, date]]:
    """Retorna lista de (data_inicio, data_fim) de períodos já reservados."""
    cal = _fetch_calendar()
    ranges = []
    for component in cal.walk():
        if component.name == "VEVENT":
            dtstart = component.get("DTSTART").dt
            dtend = component.get("DTEND").dt
            if hasattr(dtstart, "date"):
                dtstart = dtstart.date()
            if hasattr(dtend, "date"):
                dtend = dtend.date()
            ranges.append((dtstart, dtend))
    return ranges


def is_available(check_in: date, check_out: date) -> bool:
    """Verifica se o período está livre (sem sobreposição com reservas existentes)."""
    booked = get_booked_ranges()
    for start, end in booked:
        # Sobreposição: o pedido começa antes do fim da reserva E termina depois do início
        if check_in < end and check_out > start:
            return False
    return True


def next_available_windows(days_ahead: int = 90, min_nights: int = 2) -> list[dict]:
    """
    Retorna janelas livres nos próximos N dias.
    Útil para o planejador de posts sugerir datas disponíveis nas legendas.
    """
    booked = get_booked_ranges()
    today = date.today()
    end_horizon = today + timedelta(days=days_ahead)

    # Marca todos os dias ocupados
    occupied = set()
    for start, end in booked:
        current = start
        while current < end:
            occupied.add(current)
            current += timedelta(days=1)

    windows = []
    window_start = None
    current = today

    while current <= end_horizon:
        if current not in occupied:
            if window_start is None:
                window_start = current
        else:
            if window_start and (current - window_start).days >= min_nights:
                windows.append({
                    "check_in": window_start.isoformat(),
                    "check_out": current.isoformat(),
                    "nights": (current - window_start).days,
                })
            window_start = None
        current += timedelta(days=1)

    if window_start and (end_horizon - window_start).days >= min_nights:
        windows.append({
            "check_in": window_start.isoformat(),
            "check_out": end_horizon.isoformat(),
            "nights": (end_horizon - window_start).days,
        })

    return windows
