# SmartAttend — AI-Powered Face Recognition Attendance System

A desktop attendance system that marks student attendance automatically using live face recognition, with liveness (anti-spoof) checks so a printed photo or a phone screen can't fake a check-in.

## Features

- **Face-recognition attendance** — students are recognized from a live camera feed and marked present automatically, no manual roll call.
- **Liveness detection** — combines texture analysis (Laplacian variance, to reject flat/blurry printed photos) with blink detection (Eye Aspect Ratio) so a static photo or video held up to the camera is rejected.
- **Student enrollment** — capture multiple face samples per student and average them into a single reference encoding.
- **Session management** — start/stop attendance sessions, configurable confirmation streak before marking someone present, and a session timeout.
- **Reports** — attendance history and defaulter tracking, exportable to Excel and PDF.
- **Notifications** — optional email alerts on session end / defaulter checks.
- **Desktop UI** — built with `customtkinter`, dark-themed.

## How recognition works

1. **Detection** — dlib's HOG face detector locates faces in each camera frame (`ml/detector.py`).
2. **Encoding** — each detected face is converted into a 128-dimensional embedding vector via `face_recognition` (`ml/recognizer.py`).
3. **Matching** — the live encoding is compared against stored student encodings using Euclidean distance; a match is accepted if the distance is below `TOLERANCE` (default `0.6`).
4. **Liveness** — every matched face must also pass a texture check and a confirmed blink within a rolling window before attendance is marked, to block photo/video spoofing (`ml/liveness.py`).

## Tech Stack

- Python, [customtkinter](https://github.com/TomSchimansky/CustomTkinter) (UI)
- OpenCV, `face_recognition` (dlib) for detection/recognition
- SQLite for storage
- `reportlab` / `openpyxl` for PDF/Excel reports

## Getting Started

### Prerequisites
- Python 3.10+
- A webcam

### Installation

```bash
git clone https://github.com/PiyushSolanki038/SmartAttend-AI-Powered-Face-Recognition-Attendance-System.git
cd SmartAttend-AI-Powered-Face-Recognition-Attendance-System
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

On first run, the app initializes a local SQLite database and bootstraps an admin account under `~/.smartattend/`.

## Project Structure

```
smartattend/
├── main.py              # entry point
├── config.py             # app settings (ML thresholds, DB paths, report config)
├── db/                    # schema, migrations, queries
├── ml/                    # detection, recognition, liveness, camera, preprocessing
├── services/              # auth, enrollment, session, reports, notifications
└── ui/                    # customtkinter screens and components
```

## Configuration

Key tunables live in `config.py`, persisted to `~/.smartattend/settings.json`:

| Setting | Default | Purpose |
|---|---|---|
| `TOLERANCE` | 0.6 | Max face-distance for a match |
| `ATTENDANCE_CONFIRM_STREAK` | 2 | Consecutive matches needed before marking present |
| `LIVENESS_TEXTURE_MIN` | 25.0 | Minimum sharpness to pass the photo-spoof check |
| `MIN_ENCODINGS` | 3 | Minimum face samples required per enrolled student |
| `DEFAULTER_THRESHOLD` | 75.0 | Attendance % below which a student is flagged |
