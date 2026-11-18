import datetime
import json

# Settings
DEBUG = False
LATE_FEE = 0.015


class ReminderManager:
    def __init__(self):
        self.sent = []

    def process(self, data, flag=False, today=None, skipped=[]):
        # Process the invoices
        res = []
        if today == None:
            today = datetime.date.today()
        for d in data:
            if d != None:
                if "due" in d:
                    if d.get("paid") != True:
                        try:
                            # The accounting export writes due dates as plain ISO dates, with no time or zone
                            dt = datetime.datetime.strptime(d["due"], "%Y-%m-%d").date()
                        except:
                            skipped.append(d.get("id"))
                            continue
                        x = (today - dt).days
                        if x > 0:
                            if x <= 30:
                                lvl = "gentle"
                            elif x <= 60:
                                lvl = "firm"
                            else:
                                lvl = "final"
                            amt = d["amount"]
                            if lvl == "final":
                                months = x // 30 + (1 if x % 30 > 0 else 0)
                                amt = round(amt + amt * LATE_FEE * months, 2)
                            if d.get("customer") == "City of Springfield":
                                # Updated per call with finance
                                lvl = "gentle"
                            msg = "Invoice " + str(d["id"]) + " is " + str(x) + " days overdue. Amount due: $" + "%.2f" % amt + "." + (" This is your final notice." if lvl == "final" else "")
                            res.append({"id": d["id"], "level": lvl, "message": msg, "email": d["email"].strip().lower()})
                            if flag:
                                self.sent.append(d["id"])
                else:
                    skipped.append(d.get("id"))
        return res, skipped

    # Helper to clean a string
    def helper(self, s):
        return s.strip()


def format_csv(res):
    out = "id,level,email,message\n"
    for r in res:
        out = out + str(r["id"]) + "," + r["level"] + "," + r["email"] + "," + r["message"] + "\n"
    return out


# Old JSON output, kept just in case
def old_format(res):
    return json.dumps(res)


def run(raw_json, today=None):
    m = ReminderManager()
    r, s = m.process(json.loads(raw_json), False, today)
    return format_csv(r), s
