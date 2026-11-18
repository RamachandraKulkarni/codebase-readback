# Characterization tests through the public surface (run and format_csv). They record what reminders.py does today,
# bugs included, so a rewrite can prove it changed nothing.
import datetime
import json

import pytest

from reminders import format_csv, run

TODAY = datetime.date(2026, 3, 31)


def invoice_overdue_by(days_overdue, **overrides):
    due_date = TODAY - datetime.timedelta(days=days_overdue)
    return {"id": 1, "due": due_date.isoformat(), "amount": 100.0, "email": "a@example.com", **overrides}


def reminder_rows(*invoices):
    csv_text, _ = run(json.dumps(list(invoices)), TODAY)
    return csv_text.splitlines()[1:]


@pytest.mark.parametrize("days_overdue, expected_rows", [
    (-5, []),
    (0, []),
    (1, ["1,gentle,a@example.com,Invoice 1 is 1 days overdue. Amount due: $100.00."]),
    (30, ["1,gentle,a@example.com,Invoice 1 is 30 days overdue. Amount due: $100.00."]),
    (31, ["1,firm,a@example.com,Invoice 1 is 31 days overdue. Amount due: $100.00."]),
    (60, ["1,firm,a@example.com,Invoice 1 is 60 days overdue. Amount due: $100.00."]),
    (61, ["1,final,a@example.com,Invoice 1 is 61 days overdue. Amount due: $104.50. This is your final notice."]),
    (400, ["1,final,a@example.com,Invoice 1 is 400 days overdue. Amount due: $121.00. This is your final notice."]),
])
def test_reminder_level_follows_days_overdue(days_overdue, expected_rows):
    assert reminder_rows(invoice_overdue_by(days_overdue)) == expected_rows


@pytest.mark.parametrize("days_overdue, expected_amount_text", [
    (1, "Amount due: $1234.57."),
    (61, "Amount due: $1290.12. This is your final notice."),
    (90, "Amount due: $1290.12. This is your final notice."),
    (91, "Amount due: $1308.64. This is your final notice."),
])
def test_final_notice_adds_a_late_fee_per_month_started(days_overdue, expected_amount_text):
    [row] = reminder_rows(invoice_overdue_by(days_overdue, amount=1234.567))
    assert row.endswith(expected_amount_text)


def test_city_of_springfield_gets_gentle_reminders_but_keeps_the_late_fee():
    assert reminder_rows(
        invoice_overdue_by(75, customer="City of Springfield"),
        invoice_overdue_by(45, customer="City of Springfield"),
        invoice_overdue_by(75, customer="City of Springfield East"),
    ) == [
        "1,gentle,a@example.com,Invoice 1 is 75 days overdue. Amount due: $104.50.",
        "1,gentle,a@example.com,Invoice 1 is 45 days overdue. Amount due: $100.00.",
        "1,final,a@example.com,Invoice 1 is 75 days overdue. Amount due: $104.50. This is your final notice.",
    ]


def test_email_is_trimmed_and_lower_cased():
    assert reminder_rows(invoice_overdue_by(5, email="  MiXed@Example.COM\t")) == [
        "1,gentle,mixed@example.com,Invoice 1 is 5 days overdue. Amount due: $100.00."]


def test_only_a_paid_flag_equal_to_true_counts_as_paid():
    rows = reminder_rows(
        invoice_overdue_by(5, id=1, paid=True),
        invoice_overdue_by(5, id=2, paid=1),
        invoice_overdue_by(5, id=3, paid="yes"),
        invoice_overdue_by(5, id=4, paid=False),
    )
    assert [row.split(",")[0] for row in rows] == ["3", "4"]


def test_string_ids_are_printed_as_given():
    assert reminder_rows(invoice_overdue_by(5, id="INV-9")) == [
        "INV-9,gentle,a@example.com,Invoice INV-9 is 5 days overdue. Amount due: $100.00."]


def test_unusable_invoices_are_skipped_and_nulls_ignored():
    csv_text, skipped_ids = run(json.dumps([None, {"id": 7}, invoice_overdue_by(5, id=11, due="31/03/2026"), {"id": 8, "due": 20260301}]), TODAY)
    assert csv_text == "id,level,email,message\n"
    assert skipped_ids[-3:] == [7, 11, 8]


@pytest.mark.parametrize("invoice, missing_key", [
    ({"id": 9, "due": "2026-03-01", "email": "x@y"}, "amount"),
    ({"id": 9, "due": "2026-03-01", "amount": 5}, "email"),
])
def test_a_missing_amount_or_email_raises(invoice, missing_key):
    with pytest.raises(KeyError) as raised:
        run(json.dumps([invoice]), TODAY)
    assert raised.value.args == (missing_key,)


def test_csv_has_a_header_and_one_row_per_reminder():
    assert format_csv([{"id": 3, "level": "firm", "email": "z@z", "message": "m1"}, {"id": "A", "level": "final", "email": "q@q", "message": "m2"}]) == \
        "id,level,email,message\n3,firm,z@z,m1\nA,final,q@q,m2\n"
    assert format_csv([]) == "id,level,email,message\n"


def test_today_defaults_to_the_real_date():
    csv_text, _ = run(json.dumps([{"id": 5, "due": "2999-01-01", "amount": 1, "email": "f@f"}]))
    assert csv_text == "id,level,email,message\n"


def test_known_bug_skipped_ids_pile_up_across_calls():
    invoices = json.dumps([{"id": 104, "due": "20/01/2026", "amount": 75.0, "email": "c@y"}, {"id": 105, "amount": 1, "email": "d@y"}])
    _, first_skipped = run(invoices, TODAY)
    length_after_first_run = len(first_skipped)
    _, second_skipped = run(invoices, TODAY)
    assert second_skipped is first_skipped
    assert len(second_skipped) == length_after_first_run + 2
    assert second_skipped[-4:] == [104, 105, 104, 105]
