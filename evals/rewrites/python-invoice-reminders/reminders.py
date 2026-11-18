import datetime
import json
import math

GENTLE_UNTIL_DAYS_OVERDUE = 30
FIRM_UNTIL_DAYS_OVERDUE = 60
DAYS_PER_BILLING_MONTH = 30
LATE_FEE_RATE_PER_MONTH_STARTED = 0.015
SPRINGFIELD_CUSTOMER = "City of Springfield"
CSV_HEADER = "id,level,email,message\n"

# Reported, kept: one list shared by every call, so skipped ids pile up from run to run.
_skipped_invoice_ids_from_every_run = []


def run(raw_json, today=None):
    if None is today:
        today = datetime.date.today()
    reminders = _build_reminders(json.loads(raw_json), today, _skipped_invoice_ids_from_every_run)
    return format_csv(reminders), _skipped_invoice_ids_from_every_run


# res keeps its name: callers may pass it by keyword.
def format_csv(res):
    csv_rows = [
        str(reminder["id"]) + "," + reminder["level"] + "," + reminder["email"] + "," + reminder["message"] + "\n"
        for reminder in res
    ]
    return CSV_HEADER + "".join(csv_rows)


def _build_reminders(invoices, today, skipped_invoice_ids):
    reminders = []
    for invoice in invoices:
        if None is invoice:
            continue
        if "due" not in invoice:
            skipped_invoice_ids.append(invoice.get("id"))
            continue
        if True == invoice.get("paid"):
            continue
        try:
            # The accounting export writes due dates as plain ISO dates, with no time or zone
            due_date = datetime.datetime.strptime(invoice["due"], "%Y-%m-%d").date()
        except BaseException:
            # Reported, kept: this catches every error, not only a badly formatted date.
            skipped_invoice_ids.append(invoice.get("id"))
            continue
        days_overdue = (today - due_date).days
        if 0 < days_overdue:
            reminders.append(_build_reminder(invoice, days_overdue))
    return reminders


def _build_reminder(invoice, days_overdue):
    level = _reminder_level_for(days_overdue)
    amount_due = invoice["amount"]
    if "final" == level:
        amount_due = _add_late_fee(amount_due, days_overdue)
    # Reported, kept: the override comes after the late fee, so a gentle reminder can carry one.
    if SPRINGFIELD_CUSTOMER == invoice.get("customer"):
        level = "gentle"
    final_notice = " This is your final notice." if "final" == level else ""
    amount_text = "%.2f" % amount_due
    message = f"Invoice {invoice['id']} is {days_overdue} days overdue. Amount due: ${amount_text}.{final_notice}"
    return {"id": invoice["id"], "level": level, "message": message, "email": invoice["email"].strip().lower()}


def _reminder_level_for(days_overdue):
    if days_overdue <= GENTLE_UNTIL_DAYS_OVERDUE:
        return "gentle"
    if days_overdue <= FIRM_UNTIL_DAYS_OVERDUE:
        return "firm"
    return "final"


def _add_late_fee(amount, days_overdue):
    months_started = math.ceil(days_overdue / DAYS_PER_BILLING_MONTH)
    return round(amount + amount * LATE_FEE_RATE_PER_MONTH_STARTED * months_started, 2)
