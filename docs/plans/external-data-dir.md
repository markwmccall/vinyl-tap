# Plan: External Data Directory (`--data-dir`)

## Problem

`config.json` and `data/tags.json` live inside `~/vinyl-tap/`, the app directory. A reinstall (wipe and reclone) destroys them. There is no separation between application code and user data.

## Goal

- All user data lives in a configurable directory outside the app (default: `~/.local/share/vinyltap`)
- `~/vinyl-tap/` becomes pure application code — safe to wipe and reinstall freely
- `--data-dir` startup argument allows per-environment override:
  - Pi (prod): `~/.local/share/vinyltap`
  - Mac (dev): `~/.local/share/vinyltap-dev` (set in `dev-service.sh`)
  - Tests: a `tmp_path` temp directory (no side effects, no cleanup needed)
- `setup.sh` migrates existing data on first run and creates the data dir
- `install.sh` skips config creation if data dir already has a `config.json`

## What does NOT change

- `VERSION` file stays in `PROJECT_ROOT` (app metadata, not user data)
- `certs/` stays in `PROJECT_ROOT/certs/` and continues to be passed via `--ssl-cert`/`--ssl-key` (already outside config.py; can be revisited later)
- The re-register-on-tap-to-play feature is a separate plan

## Data directory layout

```
~/.local/share/vinyltap/
  config.json
  tags.json
```

No `data/` subdirectory — the whole directory is the data dir.

---

## Files to change

### 1. `core/config.py`

**Current:** `CONFIG_PATH` and `TAGS_PATH` are hardcoded relative to `__file__`.

**Changes:**
- Replace hardcoded paths with module-level vars computed from a `DATA_DIR`
- Add `set_data_dir(path)` function that updates `DATA_DIR`, `CONFIG_PATH`, `TAGS_PATH` and creates the directory

```python
# New module-level vars
DATA_DIR: Path = Path.home() / ".local" / "share" / "vinyltap"
CONFIG_PATH: str = str(DATA_DIR / "config.json")
TAGS_PATH: str = str(DATA_DIR / "tags.json")

def set_data_dir(path: str | Path) -> None:
    """Set the data directory and update derived paths. Creates the directory."""
    global DATA_DIR, CONFIG_PATH, TAGS_PATH
    DATA_DIR = Path(path).expanduser().resolve()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH = str(DATA_DIR / "config.json")
    TAGS_PATH = str(DATA_DIR / "tags.json")
```

`VERSION` remains derived from `PROJECT_ROOT = Path(__file__).parent.parent`.

No changes to `_load_config`, `_save_config`, `_load_tags`, `_save_tags` — they already use the module-level vars.

### 2. `app.py`

**Critical:** `app.py` line 28 currently does:
```python
from core.config import CONFIG_PATH, TAGS_PATH, PROJECT_ROOT, VERSION, _load_config, _save_config, _load_tags, _save_tags
```
This creates **fixed module-level bindings** for `CONFIG_PATH` and `TAGS_PATH`. After `set_data_dir()` updates `core.config.CONFIG_PATH`, these local names still point to the old values. The `nfc_service._start_nfc_thread(CONFIG_PATH)` call (line 993) and all `config_path=CONFIG_PATH` calls (lines ~426, 432, 885-898) would use stale paths.

**Fix:** Change app.py to import the module, not the names:

```python
import core.config as core_config
from core.config import PROJECT_ROOT, VERSION, _load_config, _save_config, _load_tags, _save_tags
```

Then replace all bare `CONFIG_PATH` / `TAGS_PATH` references in app.py with `core_config.CONFIG_PATH` / `core_config.TAGS_PATH`. (These are only used at startup and in a few route handlers — grep confirms ~9 occurrences total.)

**Additional changes:**
- Add `--data-dir` to argparse (after the existing args, before `args = parser.parse_args()`)
- Call `core_config.set_data_dir(args.data_dir)` as the very first thing after parsing args, before any config load

```python
parser.add_argument(
    "--data-dir",
    default=str(Path.home() / ".local" / "share" / "vinyltap"),
    help="Directory for config.json and tags.json (default: ~/.local/share/vinyltap)",
)
```

```python
args = parser.parse_args()
core_config.set_data_dir(args.data_dir)
```

### 3. `etc/vinyltap.service`

Add `--data-dir DATA_DIR` to the ExecStart line:

```ini
ExecStart=authbind --deep /home/pi/vinyl-tap/.venv/bin/python3 /home/pi/vinyl-tap/app.py --host 0.0.0.0 --port 443 --ssl-cert /home/pi/vinyl-tap/certs/PI_HOSTNAME.local.crt --ssl-key /home/pi/vinyl-tap/certs/PI_HOSTNAME.local.key --data-dir DATA_DIR
```

### 4. `scripts/setup.sh`

**Changes:**
- Define `DATA_DIR="$HOME/.local/share/vinyltap"` near the top
- Create it: `mkdir -p "$DATA_DIR"`
- Migrate existing data from old locations (before creating default config):

```bash
DATA_DIR="$HOME/.local/share/vinyltap"
mkdir -p "$DATA_DIR"

# Migrate config.json from old in-project location
if [ -f "$REPO_DIR/config.json" ] && [ ! -f "$DATA_DIR/config.json" ]; then
    cp "$REPO_DIR/config.json" "$DATA_DIR/config.json"
    echo "      Migrated config.json to $DATA_DIR"
fi

# Migrate tags.json (check both known old locations)
if [ ! -f "$DATA_DIR/tags.json" ]; then
    if [ -f "$REPO_DIR/data/tags.json" ]; then
        cp "$REPO_DIR/data/tags.json" "$DATA_DIR/tags.json"
        echo "      Migrated tags.json to $DATA_DIR"
    elif [ -f "$REPO_DIR/tags.json" ]; then
        cp "$REPO_DIR/tags.json" "$DATA_DIR/tags.json"
        echo "      Migrated tags.json to $DATA_DIR"
    fi
fi
```

- Update the config creation block (step 4/5) to write to `$DATA_DIR/config.json` instead of `$REPO_DIR/config.json`
- Add `DATA_DIR` to the sed substitution:

```bash
sed "s|/home/pi/vinyl-tap|$REPO_DIR|g; s|User=pi|User=$USERNAME|g; s|PI_HOSTNAME|$PI_HOSTNAME|g; s|DATA_DIR|$DATA_DIR|g" \
    "$REPO_DIR/etc/vinyltap.service" \
    | sudo tee /etc/systemd/system/vinyltap.service > /dev/null
```

### 5. `scripts/dev-service.sh`

Add `DATA_DIR` variable and pass it to the startup command:

```bash
DATA_DIR="$HOME/.local/share/vinyltap-dev"
```

```bash
sudo "$VENV_PYTHON" "$APP" \
  --host 0.0.0.0 --port 443 \
  --ssl-cert "$CERT" --ssl-key "$KEY" \
  --data-dir "$DATA_DIR" \
  >> "$LOG" 2>&1 &
```

### 6. `scripts/install.sh`

After extracting the release, check for existing data dir and skip config creation if already present (config creation is handled by `setup.sh`). No code change needed here — `setup.sh` already skips config creation if `$DATA_DIR/config.json` exists.

### 7. `tests/conftest.py`

Update the `temp_config` fixture to use `set_data_dir(tmp_path)` instead of separate `CONFIG_PATH`/`TAGS_PATH` monkeypatches:

```python
@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    import core.config as core_config
    core_config.set_data_dir(tmp_path)
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "sn": "3",
        "speaker_ip": "10.0.0.12",
        "speaker_name": "Family Room",
        "nfc_mode": "mock"
    }))
    return config_file
```

Any test that previously monkeypatched `TAGS_PATH` directly can drop that patch since `set_data_dir` already points TAGS_PATH at `tmp_path / "tags.json"`.

### 8. `tests/test_app.py` — TestCollection class

**Gap found:** `TestCollection` tests (~lines 1208-1250) monkeypatch `TAGS_PATH` without using the `temp_config` fixture. After this change, those tests must also call `set_data_dir`. Fix: add `temp_config` fixture parameter to each affected test, or extract the setup into the class's existing pattern. Audit all 17 `monkeypatch.setattr(core_config, "TAGS_PATH", ...)` occurrences and confirm each test either:
- Uses `temp_config` (which now calls `set_data_dir`), OR
- Explicitly calls `core_config.set_data_dir(tmp_path)` before asserting

### 9. `scripts/dev-setup.sh` — migrate existing dev data

**Gap found:** `dev-setup.sh` has no migration step. A developer who already has `config.json` at the project root (old location) would lose it on first run after this change. Add a migration block after the venv creation step:

```bash
DATA_DIR="$HOME/.local/share/vinyltap-dev"
mkdir -p "$DATA_DIR"

# Migrate config.json from old in-project location
if [ -f "$PROJECT_ROOT/config.json" ] && [ ! -f "$DATA_DIR/config.json" ]; then
    cp "$PROJECT_ROOT/config.json" "$DATA_DIR/config.json"
    echo "[+] Migrated config.json to $DATA_DIR"
fi

# Migrate tags.json (check both known old locations)
if [ ! -f "$DATA_DIR/tags.json" ]; then
    if [ -f "$PROJECT_ROOT/data/tags.json" ]; then
        cp "$PROJECT_ROOT/data/tags.json" "$DATA_DIR/tags.json"
        echo "[+] Migrated tags.json to $DATA_DIR"
    elif [ -f "$PROJECT_ROOT/tags.json" ]; then
        cp "$PROJECT_ROOT/tags.json" "$DATA_DIR/tags.json"
        echo "[+] Migrated tags.json to $DATA_DIR"
    fi
fi
```

### 10. `docs/DEVELOPMENT.md` — startup parameters

**Gap found:** `--host`, `--port`, `--ssl-cert`, `--ssl-key`, and the new `--data-dir` are not documented anywhere for developers or operators. Add a "Startup Parameters" section to DEVELOPMENT.md:

```markdown
## Startup Parameters

`app.py` accepts the following command-line arguments:

| Argument | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Host/IP to bind the Flask server |
| `--port` | `5000` | Port to bind the Flask server |
| `--ssl-cert` | _(none)_ | Path to SSL certificate file (enables HTTPS) |
| `--ssl-key` | _(none)_ | Path to SSL private key file (enables HTTPS) |
| `--data-dir` | `~/.local/share/vinyltap` | Directory for `config.json` and `tags.json` |

On the Pi, all five are set via `etc/vinyltap.service` (substituted by `setup.sh`).
On Mac dev, `--data-dir` is set to `~/.local/share/vinyltap-dev` by `dev-service.sh`.
In tests, `set_data_dir(tmp_path)` is called by the `temp_config` fixture.
```

---

## New tests to add

In `tests/test_core_config.py` (or equivalent):

- `test_set_data_dir_creates_directory` — call `set_data_dir(tmp_path / "newdir")`, assert directory exists
- `test_set_data_dir_updates_paths` — call `set_data_dir(tmp_path)`, assert `CONFIG_PATH == str(tmp_path / "config.json")` and `TAGS_PATH == str(tmp_path / "tags.json")`
- `test_set_data_dir_accepts_string` — verify string path works (not just Path object)

---

## Intermediate verification steps

**After `core/config.py` changes:**
- `grep -n "PROJECT_ROOT" core/config.py` — should only appear for VERSION, not for CONFIG_PATH/TAGS_PATH
- Run full test suite — all 381+ tests pass

**After `app.py` changes:**
- `python app.py --help` shows `--data-dir` in the output
- Run full test suite

**After `etc/vinyltap.service` changes:**
- Confirm `DATA_DIR` placeholder appears in ExecStart line
- `grep DATA_DIR etc/vinyltap.service` returns a match

**After `setup.sh` changes:**
- `grep DATA_DIR scripts/setup.sh` — appears in sed substitution and migration block
- Review migration logic handles all three old tag locations (root, `data/`, none)

**After `tests/conftest.py` + `tests/test_app.py` changes:**
- Run full test suite — all tests pass
- `grep -n "monkeypatch.*TAGS_PATH" tests/` — should return no matches (all replaced by `set_data_dir`)

**Final:**
- Full test suite passes
- Start dev server with explicit `--data-dir /tmp/test-data`, confirm it creates the directory and writes config there

---

## Order of operations

1. `core/config.py` — add `set_data_dir`, update module-level vars
2. New tests for `set_data_dir` in `tests/test_core_config.py`
3. Verify: run tests (new ones pass, existing ones pass)
4. `app.py` — fix `from ... import CONFIG_PATH` binding; add `--data-dir` arg; call `set_data_dir` at startup
5. Verify: `python app.py --help` shows `--data-dir`; run tests
6. `tests/conftest.py` — update `temp_config` fixture to use `set_data_dir(tmp_path)`
7. `tests/test_app.py` — update TestCollection and any other tests with bare `TAGS_PATH` monkeypatches
8. Verify: run tests; `grep -n "monkeypatch.*TAGS_PATH" tests/` returns nothing
9. `etc/vinyltap.service` — add `--data-dir DATA_DIR` placeholder
10. `scripts/setup.sh` — add DATA_DIR, migration, sed substitution update
11. `scripts/dev-service.sh` — add DATA_DIR variable and `--data-dir` flag
12. `scripts/dev-setup.sh` — add migration block for existing dev data
13. `docs/DEVELOPMENT.md` — add Startup Parameters section
14. Verify: run full test suite
15. Open PR
