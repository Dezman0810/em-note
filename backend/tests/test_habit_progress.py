from datetime import date

from app.services.habit_progress import habit_slots, slot_percent, smile_for_percent, window_cells


def test_five_weekdays_and_ten_reps_are_two_weeks() -> None:
    start = date(2026, 9, 7)  # Monday
    slots = habit_slots([1, 2, 3, 4, 5], 10, start)
    assert len(slots) == 10
    assert slots[0] == date(2026, 9, 7)
    assert slots[-1] == date(2026, 9, 18)
    assert (slots[-1] - slots[0]).days == 11


def test_window_is_anchor_plus_minus_ten() -> None:
    anchor = date(2026, 9, 16)
    today = date(2026, 9, 6)
    cells = window_cells(anchor, today)
    assert len(cells) == 21
    assert cells[0].day == date(2026, 9, 6)
    assert cells[10].day == anchor
    assert cells[10].is_anchor is True
    assert cells[-1].day == date(2026, 9, 26)
    assert cells[0].is_today is True


def test_smiles_and_percent() -> None:
    assert smile_for_percent(0)[0] == "🙂"
    assert smile_for_percent(100)[0] == "🤩"
    assert slot_percent(5, 10) == 50
    assert slot_percent(10, 10) == 100
