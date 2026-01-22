from __future__ import annotations

import argparse
import re
import csv
import random
import platform
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

DATE_SEP = "|"
MASTERY_STREAK = 5
DEFAULT_DATA_DIR = Path("data")


@dataclass
class WordEntry:
    word: str
    phrase: str
    history: list[str]  # YYYY-MM-DD strings

    @property
    def streak(self) -> int:
        return len(self.history)

    @property
    def mastered(self) -> bool:
        return self.streak >= MASTERY_STREAK

    def reviewed_today(self, today: str) -> bool:
        return bool(self.history) and self.history[-1] == today

    def last_review(self) -> str | None:
        return self.history[-1] if self.history else None

class Speaker:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._warned = False
        self._is_windows = platform.system().lower().startswith("win")

    def speak(self, text: str) -> None:
        if not self.enabled:
            return
        text = (text or "").strip()
        if not text:
            return

        if self._is_windows:
            self._speak_windows(text)
        else:
            self._speak_linux(text)

    def _speak_windows(self, text: str) -> None:
        # Built-in .NET speech synthesizer (no installs needed)
        safe = text.replace('"', '`"')
        ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$voice = $synth.GetInstalledVoices() | "
        "Where-Object { $_.VoiceInfo.Culture.Name -like 'de-*' } | "
        "Select-Object -First 1; "
        "if ($voice) { $synth.SelectVoice($voice.VoiceInfo.Name) }; "
        f"$synth.Speak(\"{safe}\");"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self._warn_once("[TTS] PowerShell not found; cannot speak on this Windows setup.")

    def _speak_linux(self, text: str) -> None:
        # Prefer spd-say if present, else espeak-ng/espeak
        if shutil.which("spd-say"):
            subprocess.run(["spd-say", "-l", "de", text], check=False)
            return
        
        if shutil.which("espeak-ng"):
            subprocess.run(["espeak-ng", "-v", "de", text], check=False)
            return

        if shutil.which("espeak"):
            subprocess.run(["espeak", "-v", "de", text], check=False)
            return

        for cmd in ("espeak-ng", "espeak"):
            if shutil.which(cmd):
                subprocess.run([cmd, text], check=False)
                return

        self._warn_once(
            "[TTS] No TTS engine found. On Ubuntu/Debian install one of:\n"
            "  sudo apt-get update && sudo apt-get install -y espeak-ng\n"
            "or\n"
            "  sudo apt-get update && sudo apt-get install -y speech-dispatcher\n"
            "Then rerun with --speak."
        )

    def _warn_once(self, msg: str) -> None:
        if self._warned:
            return
        self._warned = True
        print(msg)

def setup_tts_ubuntu(run_install: bool) -> None:
    """
    For Ubuntu/Debian-like systems, try to install espeak-ng via apt.
    If run_install=False, only print the command.
    """
    cmd = ["sudo", "apt-get", "update", "&&", "sudo", "apt-get", "install", "-y", "espeak-ng"]
    printable = "sudo apt-get update && sudo apt-get install -y espeak-ng"

    if not run_install:
        print("To enable TTS on Ubuntu/Debian, run:")
        print(f"  {printable}")
        return

    # Run via shell so the && works (simple, and this is a user-invoked command)
    print("Installing espeak-ng (Ubuntu/Debian)...")
    subprocess.run(printable, shell=True, check=False)


def success(text: str) -> str:
    return Fore.GREEN + text

def error(text: str) -> str:
    return Fore.RED + Style.BRIGHT + text

def highlight(text: str) -> str:
    return Fore.YELLOW + Style.BRIGHT + text

def highlight_word_in_phrase(phrase: str, word:str) -> str:
    """
    Highlight all occurrences of 'word' inside 'phrase', case-insensitive
    """
    if not phrase or not word:
        return phrase

    def repl(match: re.Match) -> str:
        return Fore.YELLOW + Style.BRIGHT + match.group(0) + Style.RESET_ALL

    pattern = re.compile(re.escape(word), re.IGNORECASE)
    return pattern.sub(repl, phrase)

def load_words(path: Path) -> dict[str, WordEntry]:
    if not path.exists():
        return {}

    entries: dict[str, WordEntry] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            word = (row.get("word") or "").strip()
            if not word:
                continue
            phrase = (row.get("phrase") or "").strip()
            history_raw = (row.get("history") or "").strip()
            history = [h for h in history_raw.split(DATE_SEP) if h] if history_raw else []
            entries[word] = WordEntry(word=word, phrase=phrase, history=history)
    return entries


def save_words(path: Path, entries: dict[str, WordEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["word", "phrase", "history"])
        writer.writeheader()
        for key in sorted(entries.keys(), key=str.lower):
            e = entries[key]
            writer.writerow(
                {"word": e.word, "phrase": e.phrase, "history": DATE_SEP.join(e.history)}
            )


def add_word(entries: dict[str, WordEntry], word: str, phrase: str) -> None:
    word = word.strip()
    phrase = phrase.strip()
    if not word:
        raise ValueError("Word must not be empty.")
    if word in entries:
        entries[word].phrase = phrase  # update phrase, keep history
    else:
        entries[word] = WordEntry(word=word, phrase=phrase, history=[])


def record_success_once_per_day(entry: WordEntry, today: str) -> None:
    if entry.reviewed_today(today):
        return
    entry.history.append(today)


def reset_streak(entry: WordEntry) -> None:
    entry.history.clear()


def get_review_queue(entries: dict[str, WordEntry], today: str) -> list[WordEntry]:
    """
    Review queue = not mastered AND not already reviewed today.
    """
    return [
        e for e in entries.values()
        if (not e.mastered) and (not e.reviewed_today(today))
    ]


def list_words(entries: dict[str, WordEntry], today: str) -> None:
    due = sorted(
        [e for e in entries.values() if not e.mastered],
        key=lambda x: (x.reviewed_today(today), x.word.lower()),
    )
    mastered = sorted([e for e in entries.values() if e.mastered], key=lambda x: x.word.lower())

    print(f"Today: {today}\n")

    print("DUE (not mastered yet):")
    if not due:
        print("  (none)")
    else:
        for e in due:
            flag = "✓ today" if e.reviewed_today(today) else " "
            last = e.last_review() or "-"
            print(f"  [{flag:6}] {e.word:20}  streak {e.streak}/{MASTERY_STREAK}  last {last}")

    print("\nMASTERED:")
    if not mastered:
        print("  (none)")
    else:
        for e in mastered:
            last = e.last_review() or "-"
            print(f"  {e.word:20}  streak {e.streak}/{MASTERY_STREAK}  last {last}")


def review(entries: dict[str, WordEntry], today: str, speaker: Speaker, limit: int | None = None) -> None:
    queue = get_review_queue(entries, today)
    already_today = len([e for e in entries.values() if (not e.mastered) and e.reviewed_today(today)])

    if not queue:
        if already_today > 0:
            print("All due words have already been reviewed today ✅")
        else:
            print("No words due. Everything is mastered 🎉")
        return

    random.shuffle(queue)
    if limit is not None:
        queue = queue[:limit]

    print(f"Today: {today}")
    if already_today:
        print(f"Already reviewed today (and therefore skipped): {already_today}")
    print(f"Reviewing now: {len(queue)} word(s). (Mastery = {MASTERY_STREAK} in a row)\n")

    for i, e in enumerate(queue, start=1):
        print("=" * 50)
        print(Style.BRIGHT + f"{i}/{len(queue)}   (current streak: {e.streak}/{MASTERY_STREAK})")
        if e.phrase:
            # print("Context sentence (read this out loud):")
            highlighted = highlight_word_in_phrase(e.phrase, e.word)
            # print(f"  {highlighted}")
            speaker.speak(f"{e.phrase} - Jetzt buchstabiere {e.word}.")
        else:
            print("No context sentence saved for this word.")
            speaker.speak("Spell the next word.")

        typed = input("Type the word: ").strip()

        if typed.lower() == e.word.lower():
            record_success_once_per_day(e, today)
            if e.mastered:
                print(f"✅ Correct! Streak: {e.streak}/{MASTERY_STREAK} — MASTERED 🎉")
            else:
                print(f"✅ Correct! Streak: {e.streak}/{MASTERY_STREAK}")
            speaker.speak("Correct!")
        else:
            reset_streak(e)
            print(f"❌ Not quite. Expected: {highlight(e.word)}. Streak reset to 0/{MASTERY_STREAK}")
            speaker.speak("Not quite.")

        print("\nDone.")


def resolve_data_file(user: str | None, file_override: str | None, data_dir: Path) -> Path:
    if file_override:
        return Path(file_override)

    if not user:
        return Path("words.csv")

    safe = "".join(ch for ch in user.strip().lower() if ch.isalnum() or ch in ("-", "_"))
    if not safe:
        safe = "user"
    return data_dir / f"{safe}.csv"


def add_loop(entries: dict[str, WordEntry]) -> None:
    print("Add mode. Type 'exitnow' to finish.\n")

    while True:
        word = input("Word: ").strip()
        if not word:
            continue
        if word.lower() == "exitnow":
            print("Leaving add mode.")
            return

        phrase = input("Phrase: ").strip()
        if phrase.lower() == "exitnow":
            print("Leaving add mode.")
            return

        add_word(entries, word, phrase)
        print(f"Saved: {word!r}\n")



def main() -> None:
    parser = argparse.ArgumentParser(description="Spelling trainer (CSV-backed, multi-user)")
    parser.add_argument("--user", help="User/profile name (e.g. daughter, son)")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Directory for user CSV files")
    parser.add_argument("--file", default=None, help="Override CSV file path (bypasses --user/--data-dir)")
    parser.add_argument("--speak", action="store_true", help="Read prompts aloud (TTS)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Add words interactively (type exitnow to stop)")

    p_review = sub.add_parser("review", help="Run a review session")
    p_review.add_argument("--limit", type=int, default=None, help="Review at most N words today")

    sub.add_parser("list", help="Show due and mastered words")
    p_setup = sub.add_parser("setup-tts", help="Help install TTS (Ubuntu/Debian)")
    p_setup.add_argument("--install", action="store_true", help="Actually run apt install (uses sudo)")


    args = parser.parse_args()

    speaker = Speaker(enabled=args.speak)
    data_dir = Path(args.data_dir)
    path = resolve_data_file(args.user, args.file, data_dir)

    entries = load_words(path)
    today = date.today().isoformat()

    if args.cmd == "add":
        add_loop(entries)
        save_words(path, entries)
        print(f"Data file: {path}")
        

    elif args.cmd == "review":
        print(f"User: {args.user or '(file override)'}")
        print(f"Data file: {path}\n")
        review(entries, today=today, speaker=speaker, limit=args.limit)
        save_words(path, entries)

    elif args.cmd == "list":
        print(f"User: {args.user or '(file override)'}")
        print(f"Data file: {path}\n")
        list_words(entries, today=today)

    elif args.cmd == "setup-tts":
        setup_tts_ubuntu(run_install=args.install)
        return


if __name__ == "__main__":
    main()
