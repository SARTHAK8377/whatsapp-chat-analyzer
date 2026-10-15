"""Generate fake WhatsApp exports (Android group, iOS 1:1) for testing."""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

random.seed(7)
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

LINES = [
    "kya scene hai aaj", "haan bhai main aa raha hu", "kal milte hai?", "ok done 👍",
    "arre yaar traffic bahut hai 😩", "pizza order kar de", "movie dekhne chalein?",
    "lol 😂😂", "send the notes please", "exam kab hai?", "bas thoda late hoga",
    "good morning ☀️", "check this https://example.com/article", "haha sahi hai",
    "kaha ho sab?", "chai peene chalte hai ☕", "cricket match dekha? 🏏",
    "deadline friday ko hai", "mujhe nahi pata yaar", "bhai sach mein? 😮",
    "ghar pahunch gaya", "weekend plan kya hai?", "ye dekh 😂", "gym ja raha hu 💪",
]
SPECIAL = {
    "Rahul": ["cricket", "match", "score", "bowling"],
    "Priya": ["assignment", "library", "notes", "submit"],
    "Dr: Sharma": ["clinic", "patients", "duty", "shift"],
    "‪+91 98765 43210‬": ["delivery", "parcel", "address"],
}
people = list(SPECIAL)
weights = [5, 4, 2, 1]


def android_ts(dt):
    h = dt.hour % 12 or 12
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year % 100:02d}, {h}:{dt.minute:02d} {'am' if dt.hour < 12 else 'pm'}"


rows = []
t = datetime(2024, 1, 5, 10, 0)
rows.append(f"{android_ts(t)} - Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them. Learn more.")
rows.append(f"{android_ts(t)} - Rahul created group \"Hostel Gang\"")
rows.append(f"{android_ts(t)} - Rahul added Priya, Dr: Sharma, ‪+91 98765 43210‬ and Ankit")
end = datetime(2024, 9, 30)
day = t
while day < end:
    # activity drops sharply after June
    rate = 0.85 if day < datetime(2024, 6, 15) else 0.35
    if random.random() < rate:
        cur = day.replace(hour=random.choice([9, 13, 18, 21, 23, 0, 1]), minute=random.randint(0, 59))
        if cur.hour < 5:
            cur += timedelta(days=1)
        speaker = random.choices(people, weights)[0]
        for _ in range(random.randint(3, 25)):
            if random.random() < 0.3:
                pass  # double text
            else:
                speaker = random.choices(people, weights)[0]
            r = random.random()
            if r < 0.06:
                text = "<Media omitted>"
            elif r < 0.08:
                text = "This message was deleted"
            elif r < 0.10:
                text = random.choice(LINES) + " <This message was edited>"
            elif r < 0.13:
                text = "first line\nsecond line: with a colon\nthird line"
            elif r < 0.45:
                text = f"{random.choice(SPECIAL[speaker])} {random.choice(LINES)}"
            else:
                text = random.choice(LINES)
            rows.append(f"{android_ts(cur)} - {speaker}: {text}")
            cur += timedelta(minutes=int(random.lognormvariate(1.2, 1.3)))
    if day.date() == datetime(2024, 3, 1).date():
        rows.append(f"{android_ts(cur)} - Priya changed the subject from \"Hostel Gang\" to \"Note: Hostel Gang 2.0\"")
    if day.date() == datetime(2024, 5, 1).date():
        rows.append(f"{android_ts(cur)} - Ankit left")
        rows.append(f"{android_ts(cur)} - Neha joined using this group's invite link")
    day += timedelta(days=1)
(out / "android_group.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")

# iOS 1:1, month-first (US) dates, seconds, ‎ marks
rows = []
t = datetime(2024, 2, 1, 20, 0, 0)


def ios_ts(dt):
    h = dt.hour % 12 or 12
    return f"[{dt.month}/{dt.day}/{dt.year % 100}, {h}:{dt.minute:02d}:{dt.second:02d} {'AM' if dt.hour < 12 else 'PM'}]"


rows.append(f"{ios_ts(t)} Meera: ‎Messages and calls are end-to-end encrypted. No one outside of this chat, not even WhatsApp, can read or listen to them.")
day = t
while day < datetime(2024, 7, 1):
    if random.random() < 0.7:
        cur = day.replace(hour=random.choice([8, 12, 19, 22, 1]), minute=random.randint(0, 59), second=random.randint(0, 59))
        if cur.hour < 5:
            cur += timedelta(days=1)
        sp = random.choice(["Meera", "Arjun"])
        for _ in range(random.randint(2, 15)):
            if random.random() < 0.65:
                sp = "Arjun" if sp == "Meera" else "Meera"
            r = random.random()
            if r < 0.05:
                rows.append(f"‎{ios_ts(cur)} {sp}: ‎image omitted")
            elif r < 0.07:
                rows.append(f"‎{ios_ts(cur)} {sp}: ‎<attached: 00000012-PHOTO-2024-03-02-19-22-10.jpg>")
            elif r < 0.08:
                rows.append(f"{ios_ts(cur)} {sp}: ‎This message was deleted.")
            else:
                rows.append(f"{ios_ts(cur)} {sp}: {random.choice(LINES)}")
            cur += timedelta(seconds=int(random.lognormvariate(4.5, 1.4)))
    day += timedelta(days=1)
(out / "ios_chat.txt").write_text("\r\n".join(rows) + "\r\n", encoding="utf-8-sig", newline="")
print("ok")
