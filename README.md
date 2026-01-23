# Spelling Trainer (CLI)

A small, offline spelling trainer for children.

The program:
- stores words and example phrases in CSV files
- supports multiple users (e.g. different children)
- tracks daily review streaks
- prevents reviewing the same word more than once per day
- supports spoken prompts (Text-to-Speech)
- works on **Windows** and **Linux (Ubuntu/Debian)**

This project is intentionally simple, robust, and kid-friendly.

---

## Features

- **Add mode**: enter new words and example phrases
- **Review mode**:
  - word is spoken
  - child types the word
  - progress is saved immediately
  - after 5 correct days in a row, a word is mastered
- **Quit safely** at any time (`q`) without losing progress
- **Replay prompt** (`a`) if the word needs to be heard again
- **Multi-user support** via separate CSV files
- **German and English UI** (via CSV-based localization)

---

## Quick start (recommended for kids)

If you received this as a ZIP:

1. Unzip the folder anywhere (e.g. `Documents\spelling-trainer`)
2. Double-click:
   - `run-sophia.ps1` or
   - `run-jakob.ps1`

The first run will:
- create a virtual environment
- install required Python packages
- start the trainer automatically

Every run after that is instant.

> ⚠️ On Windows, PowerShell may block scripts once.
> Run this **once** in PowerShell (no admin needed):
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

---

## Requirements

- **Python 3.10+**
  - Windows: https://www.python.org/downloads/
  - Linux: usually preinstalled (`python3`)
- No internet connection required for daily use

---

## Manual setup (for parents / developers)

### 1. Clone the repository

```bash
git clone https://github.com/beckoningstranger/spelling-trainer.git
cd spelling-trainer
```

---

### 2. Create a virtual environment

#### Windows (PowerShell)
```powershell
python -m venv .venv
```

#### Linux / Ubuntu
```bash
python3 -m venv .venv
```

---

### 3. Activate the virtual environment

#### Windows (PowerShell)
```powershell
.venv\Scripts\Activate.ps1
```

#### Linux / Ubuntu
```bash
source .venv/bin/activate
```

You should now see `(.venv)` in your shell prompt.

---

### 4. Install dependencies

```bash
pip install colorama
```

---

### 5. Run the program

```bash
python spelling-trainer.py --user sophia --language de --speak review
```

---

## Command overview

```text
spelling-trainer.py [OPTIONS] {add,review,list,setup-tts}
```

### Common options
- `--user NAME` – user profile (creates `data/NAME.csv`)
- `--language en|de` – UI language
- `--speak` – enable spoken prompts (TTS)

### Modes

#### Add words
```bash
python spelling-trainer.py --user sophia --language de add
```

Type words and phrases repeatedly.  
Enter `exitnow` to leave add mode.

---

#### Review words
```bash
python spelling-trainer.py --user sophia --language de --speak review
```

During review:
- type the word → check answer
- `a` → play prompt again
- `q` → quit safely (progress already saved)

---

#### List progress
```bash
python spelling-trainer.py --user sophia --language de list
```

Shows:
- words still due
- words already mastered

---

## Text-to-Speech (TTS)

### Windows
Uses built-in Windows voices (offline).

To improve quality:
- install German language voices via Windows Settings
- slower speech rate is used automatically

### Linux (Ubuntu/Debian)
Install one of:

```bash
sudo apt-get install espeak-ng
```

or

```bash
sudo apt-get install speech-dispatcher
```

---

## Data storage

- All progress is stored in simple CSV files
- One file per user in the `data/` directory
- UTF-8 encoded (safe for Umlauts and ß)
- Progress is saved **immediately** after every answer

Example:
```
data/
 ├─ sophia.csv
 └─ jakob.csv
```

---

## Philosophy

This tool is intentionally:
- small
- offline
- understandable
- robust against crashes

No databases, no accounts, no cloud, no tracking.

---

## License

Private / family use.  
Feel free to adapt for personal or educational purposes.
