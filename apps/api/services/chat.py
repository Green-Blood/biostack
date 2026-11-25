"""Ask-the-AI-about-my-record: the owner's whole record as compact text, sent ahead of each question."""
import datetime as dt

from sqlmodel import Session, select

from db.models import LabReport
from services.data_export import record_texts

MAX_QUESTION_CHARS = 4000

SYSTEM = (
    "You answer questions from one person about their own health, using their personal record that follows. "
    "The record is plain text: profile.md (age, sex, height, weight), biomarkers.csv (every lab result with the "
    "reference range the lab printed; 'out of range' was computed from it), courses.csv (medicines and supplements), "
    "records.md (visits, hospital stays, diagnoses, treatments, notes) and body.csv. "
    "Use the record when it is relevant and cite each fact you used inline in square brackets with its file and row identity, for example [biomarkers.csv: Ferritin 2025-03-14] or [records.md: visit 2025-06-02]; never cite a source that is not in the record. Results older than a year or so are history, "
    "not the present state: say how old they are. You are not a doctor and must not diagnose: describe what something "
    "might be, what would make it more or less worrying, and what to ask or show a doctor, and say plainly when it "
    "should be seen soon. If the question is about something visible in a photo, describe what you see and its limits. "
    "If the record lacks what you need, say so instead of guessing. Be brief and plain. Write plain text only: no markdown "
    "(no **bold**, no tables) and no LaTeX; write units like 10^12/L as ordinary text. Answer in the language the question "
    "is written in; when unsure, use the language the person's interface uses. "
    "Today’s date is given in the record. Offer to record data only when the person clearly asks. "
    "All offers are proposals requiring confirmation; never say anything was saved. Briefly describe each proposal."
)


LANGUAGE_NOTES = {"ru": " The person's interface is in Russian: answer in Russian unless the question is clearly in another language."}


def record_context(session: Session, today: dt.date | None = None) -> str:
    """The same text every time while the record is unchanged, so the provider can cache it between questions."""
    today = today or dt.date.today()
    reports = {r.id: r for r in session.exec(select(LabReport)).all()}
    texts, _ = record_texts(session, reports, {}, {}, today)
    return f"Today: {today.isoformat()}\n\n" + "\n\n".join(f"=== {name} ===\n{text.strip()}" for name, text in texts.items())
