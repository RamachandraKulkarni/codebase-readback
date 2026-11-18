import datetime

from reminders import run

invoices = """[
  {"id": 101, "due": "2026-01-10", "amount": 120.0, "email": " Ann@Example.com ", "customer": "Ann's Bakery"},
  {"id": 102, "due": "2025-11-01", "amount": 900.0, "email": "ops@springfield.gov", "customer": "City of Springfield"},
  {"id": 103, "due": "2026-01-20", "amount": 50.0, "email": "bo@example.com", "paid": true},
  {"id": 104, "due": "20/01/2026", "amount": 75.0, "email": "cy@example.com"},
  {"id": 105, "amount": 10.0, "email": "di@example.com"}
]"""
csv_text, skipped_ids = run(invoices, today=datetime.date(2026, 2, 1))
print(csv_text, end="")
print("skipped", skipped_ids)
csv_text, skipped_ids = run(invoices, today=datetime.date(2026, 2, 1))
print("skipped on the second run", skipped_ids)
