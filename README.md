# Quakeworld Mindbug

A structured **experimental** external QuakeWorld client controller, designed for Team Fortress bot research.

## What works / what does not

- **Implemented:** Linux FIFO command transport, focused Windows keyboard/mouse input, optional ezQuake process launch, connection command, movement state management, seeded exploration, UDP telemetry parsing, stuck heuristic, persistent SQLite waypoint graph, directed graph routing, CLI, unit tests.
- **Not implemented:** ezQuake-side telemetry exporter, actual collision detection, map/BSP parsing, path following, enemy perception, aiming, shooting, Team Fortress objectives, automated team/class selection, server protocol client, true headless mode, reinforcement learning.
- **Important:** The stock ezQuake FIFO feature and the `rotate` console command need verification with your particular build. No actual game integration was tested here. The project **cannot learn a map from a stock ezQuake client alone**; the telemetry interface is a proposed contract for a future client modification.
- **Graph caution:** edges are inferred between successive samples, not verified walkable routes. Sampling too slowly can create false edges; route finding is currently an offline API, not used to drive the bot.

## Requirements

- Python 3.10+ on Linux or Windows; no runtime third-party Python dependencies.
- On Linux, a compatible ezQuake client exposing a FIFO at `/tmp/ezquake_<username>` (verify on your installation).
- On Windows, an ezQuake client accepting synthetic keyboard/mouse input, running at the same privilege level as the bot.
- Your own QuakeWorld/TF server, or permission to use automation.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

## Basic run

Start ezQuake and join your server. Then:

```bash
qwbot --mode test --duration 5
qwbot --mode explore --duration 60 --seed 42
qwbot --server 127.0.0.1:27500 --mode explore --duration 120
```

Optional process launch (starts the client but **does not** make it headless):

```bash
qwbot --launch /path/to/ezquake --mode explore --duration 30
```

The process is deliberately left running when the controller stops. If the FIFO is absent, the controller exits with an error. If movement commands do not work, check ezQuake console support and command names.

## Windows (PowerShell)

Install once from the project directory with your virtual environment active:

```powershell
python -m pip install -e .
```

Launch the client from the parent Quakeworld folder:

```powershell
python -m qwbot --launch ..\ezquake.exe --map dm6 --timeout 30 --mode explore --duration 60
```

The client starts with its executable directory as its working directory so it
can find its game data. `--map dm6` passes `+map dm6` to load a local map instead
of staying in the menu; use the name of a map installed in your active game.
`--map` requires `--launch` and cannot be combined with `--server`.
Use `--server 127.0.0.1:27500` instead to connect at launch, or
join your permitted server manually. For an already-running client, join first,
then run without `--launch` and switch back to ezQuake:

```powershell
python -m qwbot --timeout 30 --mode explore --duration 60
```

Windows automatically selects input control instead of FIFO. Focus the actual
game window before `--timeout` expires, with the console and menus closed.
Movement starts as soon as the game is focused (after `--connect-wait` when
launching with `--server` or `--map`). Increase `--connect-wait` if loading takes
longer; it defaults to five seconds and does not detect loading completion.
The bot does not join a team or select a class.
For an existing client, its current name and connection are retained;
`--server` requires `--launch`.

The following bindings must be configured in the ezQuake console beforehand:

```text
bind w +forward
bind a +moveleft
bind d +moveright
bind SPACE +jump
```

Keep the game focused and do not use the keyboard or mouse while the bot runs.
**Hold F12 or switch away from ezQuake to stop**; held bot keys are released.
Opening the in-game console/menu does not change window focus, so stop the bot
before doing that. The game process remains running when the bot exits.

Turning uses relative mouse movement, not the Linux `rotate` command.
`--mouse-counts-per-degree` defaults to 15.15, approximately appropriate for
`sensitivity 3` and `m_yaw 0.022` with unaccelerated input. Adjust it for your
settings; exact angles and acceptance of injected input depend on the client
build and mouse settings. Real game movement has not been verified automatically.
This adds Windows control, not perception, aiming, or autonomous gameplay.

## Optional telemetry protocol (not in stock ezQuake)

A future ezQuake patch or local bridge can send UTF-8 JSON UDP datagrams to `127.0.0.1:27999`:

```json
{"map":"2fort5","origin":[100.0,200.0,24.0],"yaw":90.0,"health":100,"on_ground":true}
```

Run:

```bash
qwbot --telemetry --database navigation.sqlite3 --mode explore --duration 120
```

With the bot running, you can separately test the telemetry receiver using:

```bash
python examples/send_fake_telemetry.py
```

This sends **fake** positions; they are not sourced from the game and will pollute the navigation database. Use a disposable database for this test. Telemetry is local-only and has no authentication.

## Project layout

```text
src/qwbot/
  cli.py          command line, orchestration and optional launch
  transport.py    FIFO console and in-memory testing adapter
  windows.py      focused Windows input and emergency-stop handling
  controller.py   movement commands and safe key releases
  models.py       shared dataclasses
  brain.py        deterministic exploration and basic stuck response
  telemetry.py    proposed UDP JSON telemetry contract
  navigation.py   SQLite waypoint graph and route query
  __main__.py     python -m qwbot entrypoint
tests/             stdlib unittest tests
examples/          sample telemetry and fake sender
```

## Suggested v0.3 priorities

1. Verify FIFO control against an actual ezQuake Linux build.
2. Implement ezQuake-side state exporter with origin, velocity, view angles, map name, and collision/trace results.
3. Add timestamp freshness, movement acknowledgement, and safety stop when telemetry disappears.
4. Parse BSP geometry and build validated navigation connectivity rather than connecting arbitrary samples.
5. Implement navigation execution and class/objective adapters for Team Fortress.

This project is a development scaffold, **not** a complete autonomous playable bot.
