from __future__ import annotations

import argparse
import csv
import platform
import random
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from colorama import Fore, Style, init

init(autoreset=True)

DATE_SEP = "|"
MASTERY_STREAK = 5
DEFAULT_DATA_DIR = Path("data")


# ----------------------------
# Data model
# ----------------------------
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


# ----------------------------
# i18n (Key,English,German)
# ----------------------------
class I18N:
    def __init__(self, language: str, translations: dict[str, dict[str, str]]):
        self.language = language
        self.translations = translations

    def t(self, key: str, **kwargs) -> str:
        entry = self.translations.get(key)
        if not entry:
            # Make missing keys obvious during development
            text = key
        else:
            text = entry.get(self.language) or entry.get("en") or key
        try:
            return text.format(**kwargs)
        except KeyError:
            # If formatting vars are missing, still show something useful
            return text


def load_translations_csv(path: Path) -> dict[str, dict[str, str]]:
    """
    CSV columns: Key,English,German
    Returns: { key: { "en": English, "de": German } }
    """
    if not path.exists():
        return {}

    out: dict[str, dict[str, str]] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("Key") or "").strip()
            en = (row.get("English") or "").strip()
            de = (row.get("German") or "").strip()
            if key:
                out[key] = {"en": en, "de": de}
    return out


# ----------------------------
# TTS Speaker (Windows + Linux)
# ----------------------------
import subprocess
import platform
import shutil

class Speaker:
    def __init__(self, enabled: bool, language: str):
        self.enabled = enabled
        self.language = language  # "en" or "de"
        self._warned = False
        self._is_windows = platform.system().lower().startswith("win")
        self._proc: subprocess.Popen | None = None

    def stop(self) -> None:
        """Stop any current speech."""
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._proc = None

    def speak_async(self, text: str) -> None:
        """Start speaking and return immediately."""
        if not self.enabled:
            return
        text = (text or "").strip()
        if not text:
            return

        # Stop any previous prompt so prompts don't overlap
        self.stop()

        if self._is_windows:
            self._proc = self._spawn_windows(text)
        else:
            self._proc = self._spawn_linux(text)

        if self._proc is None:
            self._warn_once("[TTS] Could not start speech (no engine found).")

    def speak_and_wait(self, text: str) -> None:
        self.speak_async(text)
        if self._proc:
            self._proc.wait()

    def speak_many_and_wait(self, parts: list[str], pause: str = ". ") -> None:
        merged = pause.join(p.strip() for p in parts if p and p.strip())
        self.speak_and_wait(merged)

    def speak_many_async(self, parts: list[str], pause: str = ". ") -> None:
        merged = pause.join(p.strip() for p in parts if p and p.strip())
        self.speak_async(merged)

    # ---------- platform spawners ----------

    def _spawn_windows(self, text: str) -> subprocess.Popen | None:
        safe = text.replace('"', '`"')
        culture_prefix = "de-*" if self.language == "de" else "en-*"

        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voice = $synth.GetInstalledVoices() | "
            f"Where-Object {{ $_.VoiceInfo.Culture.Name -like '{culture_prefix}' }} | "
            "Select-Object -First 1; "
            "if ($voice) { $synth.SelectVoice($voice.VoiceInfo.Name) }; "
            f"$synth.Speak(\"{safe}\");"
        )

        try:
            return subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self._warn_once("[TTS] PowerShell not found; cannot speak on this Windows setup.")
            return None

    def _spawn_linux(self, text: str) -> subprocess.Popen | None:
        lang = "de" if self.language == "de" else "en"

        # IMPORTANT: no --wait here (we WANT it async)
        if shutil.which("spd-say"):
            return subprocess.Popen(["spd-say", "-l", lang, text],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if shutil.which("espeak-ng"):
            return subprocess.Popen(["espeak-ng", "-v", lang, text],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if shutil.which("espeak"):
            return subprocess.Popen(["espeak", "-v", lang, text],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        self._warn_once(
            "[TTS] No TTS engine found. On Ubuntu/Debian install:\n"
            "  sudo apt-get update && sudo apt-get install -y espeak-ng\n"
            "or\n"
            "  sudo apt-get update && sudo apt-get install -y speech-dispatcher\n"
        )
        return None

    def _warn_once(self, msg: str) -> None:
        if self._warned:
            return
        self._warned = True
        print(msg)



def setup_tts_ubuntu(run_install: bool, i18n: I18N) -> None:
    printable = "sudo apt-get update && sudo apt-get install -y espeak-ng"

    if not run_install:
        print(i18n.t("TTS_SETUP_INSTRUCTIONS"))
        print(f"  {printable}")
        return

    print(i18n.t("TTS_SETUP_INSTALLING"))
    subprocess.run(printable, shell=True, check=False)


# ----------------------------
# Terminal helpers
# ----------------------------
def success(text: str) -> str:
    return Fore.GREEN + text


def error(text: str) -> str:
    return Fore.RED + Style.BRIGHT + text


def highlight(text: str) -> str:
    return Fore.YELLOW + Style.BRIGHT + text


def highlight_word_in_phrase(phrase: str, word: str) -> str:
    if not phrase or not word:
        return phrase

    def repl(match: re.Match) -> str:
        return Fore.YELLOW + Style.BRIGHT + match.group(0) + Style.RESET_ALL

    pattern = re.compile(re.escape(word), re.IGNORECASE)
    return pattern.sub(repl, phrase)


# ----------------------------
# CSV persistence (words)
# ----------------------------
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
            writer.writerow({"word": e.word, "phrase": e.phrase, "history": DATE_SEP.join(e.history)})


def add_word(entries: dict[str, WordEntry], word: str, phrase: str) -> None:
    word = word.strip()
    phrase = phrase.strip()
    if not word:
        raise ValueError("Word must not be empty.")
    if word in entries:
        entries[word].phrase = phrase
    else:
        entries[word] = WordEntry(word=word, phrase=phrase, history=[])


def record_success_once_per_day(entry: WordEntry, today: str) -> None:
    if entry.reviewed_today(today):
        return
    entry.history.append(today)


def reset_streak(entry: WordEntry) -> None:
    entry.history.clear()


def get_review_queue(entries: dict[str, WordEntry], today: str) -> list[WordEntry]:
    return [e for e in entries.values() if (not e.mastered) and (not e.reviewed_today(today))]


# ----------------------------
# App modes
# ----------------------------
def add_loop(entries: dict[str, WordEntry], i18n: I18N) -> None:
    print(i18n.t("ADD_MODE_TITLE") + "\n")

    while True:
        word = input(i18n.t("WORD_PROMPT") + " ").strip()
        if not word:
            continue
        if word.lower() == "exitnow":
            print(i18n.t("LEAVING_ADD"))
            return

        phrase = input(i18n.t("PHRASE_PROMPT") + " ").strip()
        # (we only treat exitnow in the word prompt; phrases may contain that string)
        add_word(entries, word, phrase)
        print(f"{i18n.t('SAVED')} {word}\n")


def list_words(entries: dict[str, WordEntry], today: str, i18n: I18N) -> None:
    due = sorted(
        [e for e in entries.values() if not e.mastered],
        key=lambda x: (x.reviewed_today(today), x.word.lower()),
    )
    mastered = sorted([e for e in entries.values() if e.mastered], key=lambda x: x.word.lower())

    print(i18n.t("TODAY", today=today) + "\n")

    print(i18n.t("DUE_TITLE"))
    if not due:
        print("  " + i18n.t("NONE"))
    else:
        for e in due:
            flag = i18n.t("TODAY_FLAG") if e.reviewed_today(today) else " "
            last = e.last_review() or "-"
            print(f"  [{flag:6}] {e.word:20}  {i18n.t('STREAK', s=e.streak, m=MASTERY_STREAK)}  {i18n.t('LAST', last=last)}")

    print("\n" + i18n.t("MASTERED_TITLE"))
    if not mastered:
        print("  " + i18n.t("NONE"))
    else:
        for e in mastered:
            last = e.last_review() or "-"
            print(f"  {e.word:20}  {i18n.t('STREAK', s=e.streak, m=MASTERY_STREAK)}  {i18n.t('LAST', last=last)}")


def review(entries: dict[str, WordEntry], today: str, speaker: Speaker, i18n: I18N, limit: int | None = None) -> None:
    queue = get_review_queue(entries, today)
    already_today = len([e for e in entries.values() if (not e.mastered) and e.reviewed_today(today)])

    if not queue:
        if already_today > 0:
            print(i18n.t("ALL_DONE_TODAY"))
        else:
            print(i18n.t("NO_WORDS_DUE"))
        return

    random.shuffle(queue)
    if limit is not None:
        queue = queue[:limit]

    # Only print session header if not speaking (prevents “peeking”)
    if not speaker.enabled:
        print(i18n.t("TODAY", today=today))
        if already_today:
            print(i18n.t("ALREADY_REVIEWED_TODAY", n=already_today))
        print(i18n.t("REVIEW_START", n=len(queue), m=MASTERY_STREAK) + "\n")

    for idx, e in enumerate(queue, start=1):
        if speaker.enabled:
            if e.phrase:
                # Speak prompt while allowing typing immediately
                speaker.speak_many_async([e.phrase, f"{i18n.t('SAY_SPELL_NOW')} {e.word}"])
            else:
                speaker.speak_async(i18n.t("SAY_NEXT_WORD"))

            # Use a neutral prompt so the kid doesn't get hints from screen text
            typed = input("> ").strip()

            # Stop prompt as soon as they finish typing (optional, but nicer)
            speaker.stop()
        else:
            # Text mode: show the phrase with the word highlighted (your earlier request)
            print("=" * 50)
            print(Style.BRIGHT + i18n.t("PROGRESS", i=idx, n=len(queue), s=e.streak, m=MASTERY_STREAK))
            if e.phrase:
                highlighted = highlight_word_in_phrase(e.phrase, e.word)
                print("  " + highlighted)
            else:
                print(i18n.t("NO_PHRASE"))

            input(i18n.t("PRESS_ENTER") + " ")
            typed = input(i18n.t("TYPE_WORD") + " ").strip()

        if typed.lower() == e.word.lower():
            record_success_once_per_day(e, today)
            if speaker.enabled:
                speaker.speak(i18n.t("CORRECT"))
            else:
                if e.mastered:
                    print(success(i18n.t("MASTERED_NOW", s=e.streak, m=MASTERY_STREAK)))
                else:
                    print(success(i18n.t("CORRECT_STREAK", s=e.streak, m=MASTERY_STREAK)))
        else:
            reset_streak(e)
            if speaker.enabled:
                speaker.speak(i18n.t("WRONG"))
            else:
                print(error(i18n.t("WRONG")))
                print(error(i18n.t("EXPECTED", word=highlight(e.word))))
                print(error(i18n.t("RESET_STREAK", m=MASTERY_STREAK)))

    if not speaker.enabled:
        print("\n" + i18n.t("DONE"))


# ----------------------------
# Multi-user file selection
# ----------------------------
def resolve_data_file(user: str | None, file_override: str | None, data_dir: Path) -> Path:
    if file_override:
        return Path(file_override)

    if not user:
        return Path("words.csv")

    safe = "".join(ch for ch in user.strip().lower() if ch.isalnum() or ch in ("-", "_"))
    if not safe:
        safe = "user"
    return data_dir / f"{safe}.csv"


# ----------------------------
# CLI
# ----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Spelling trainer (CSV-backed, multi-user)")
    parser.add_argument("--user", help="User/profile name (e.g. daughter, son)")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Directory for user CSV files")
    parser.add_argument("--file", default=None, help="Override CSV file path (bypasses --user/--data-dir)")

    parser.add_argument("--speak", action="store_true", help="Read prompts aloud (TTS)")

    parser.add_argument("--language", choices=["en", "de"], required=True, help="UI language (en or de)")
    parser.add_argument("--i18n-file", default="locales.csv", help="Translation CSV file (Key,English,German)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("add", help="Add words interactively (type exitnow to stop)")

    p_review = sub.add_parser("review", help="Run a review session")
    p_review.add_argument("--limit", type=int, default=None, help="Review at most N words today")

    sub.add_parser("list", help="Show due and mastered words")

    p_setup = sub.add_parser("setup-tts", help="Help install TTS (Ubuntu/Debian)")
    p_setup.add_argument("--install", action="store_true", help="Actually run apt install (uses sudo)")

    args = parser.parse_args()

    translations = load_translations_csv(Path(args.i18n_file))
    i18n = I18N(language=args.language, translations=translations)

    speaker = Speaker(enabled=args.speak, language=args.language)
    if speaker.enabled and args.user:
        speaker.speak_many_and_wait([f"{i18n.t('WELCOME')} {args.user}", i18n.t('LETSGO')])


    data_dir = Path(args.data_dir)
    path = resolve_data_file(args.user, args.file, data_dir)

    entries = load_words(path)
    today = date.today().isoformat()

    try:

        if args.cmd == "add":
            add_loop(entries, i18n)
            save_words(path, entries)
            print(i18n.t("DATA_FILE", path=path))

        elif args.cmd == "review":
            if not speaker.enabled:
                print(i18n.t("USER", user=args.user or "(file override)"))
                print(i18n.t("DATA_FILE", path=path) + "\n")
            review(entries, today=today, speaker=speaker, i18n=i18n, limit=args.limit)
            save_words(path, entries)

        elif args.cmd == "list":
            print(i18n.t("USER", user=args.user or "(file override)"))
            print(i18n.t("DATA_FILE", path=path) + "\n")
            list_words(entries, today=today, i18n=i18n)

        elif args.cmd == "setup-tts":
            setup_tts_ubuntu(run_install=args.install, i18n=i18n)
            return
    
    except KeyboardInterrupt:
        print("\n" + i18n.t("CANCELLED"))
        return


if __name__ == "__main__":
    main()
