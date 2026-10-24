# Smart Queue Token System

A web-based queue management system: customers get tokens, staff call them from counters,
and a display board shows who is being served. **No installation of packages is required** -
only Python 3.8 or newer.

## Run in VS Code
1. Unzip the folder and open it in VS Code (File > Open Folder > `smart-queue-system`).
2. Open a terminal (Terminal > New Terminal) and run:
   - Windows: `python app.py` (or `py app.py`)
   - macOS/Linux: `python3 app.py`
3. Your browser opens at http://127.0.0.1:8000 (if not, open that link manually).
4. Stop the server with `Ctrl + C`.

Or press **F5** in VS Code (Python extension installed) to run it with the debugger.

If port 8000 is busy: `python app.py --port 8080`.
To open from a phone on the same Wi-Fi: `python app.py --host 0.0.0.0` and visit `http://<your-pc-ip>:8000`.

## How to demo
1. **Get Token** tab: create tokens (try Normal, Senior and Emergency priorities).
2. **Staff Counter** tab: choose service + counter, press *Call Next Token*. Emergency/senior tokens
   are called first, but long-waiting normal tokens gradually catch up (aging).
3. Press *Complete* or *Skip / No-show*.
4. **Track Token** shows position and estimated wait; **Display Board** shows live status
   (tick the voice box to hear announcements); **Statistics** shows daily numbers.

## The "smart" part
- **Priority score** = priority weight x 15 + minutes waited. Emergency=3, Senior/Differently abled=2, Normal=1.
- **Aging** stops normal customers from waiting forever.
- **Wait estimate** = people ahead x average service time (learned from the last 10 completed
  tokens) / number of active counters.

## Project structure
- `app.py` - server, database (SQLite `queue.db`, created automatically) and queue logic
- `static/index.html` - the whole user interface
- `tests/test_queue.py` - run with `python -m unittest discover tests -v`

To reset all data, stop the server and delete `queue.db`.
