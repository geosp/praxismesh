"""The agent benchmark tasks (plan §8; RFC Phase 1: Agent benchmark suite).

Seeded from the Pre-0 spike's ten tasks (spikes/harness-vllm/tasks.py), adapted
to the sample MCP server's tool names (`lookup_price`, `lookup_stock`); its data
is the same. Each task needs an MCP call, a shell command and a file edit, and
has a deterministic check that reads only the task's final workspace.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sample_mcp.server import DISCOUNTS, PRICES, SETTINGS, STOCK

STAMP = """import hashlib, sys
p = sys.argv[1]
print("STAMP-" + hashlib.sha256(open(p, "rb").read()).hexdigest()[:12])
"""


def stamp_of(path: Path) -> str:
    return "STAMP-" + hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def read(d: Path, name: str) -> str:
    p = d / name
    return p.read_text().strip() if p.exists() else ""


@dataclass
class Task:
    id: str
    prompt: str
    files: dict[str, str]
    check: Callable[[Path], tuple[bool, str]]


def c_order_total(d: Path) -> tuple[bool, str]:
    want = f"{3 * PRICES['SKU-1'] + 2 * PRICES['SKU-4'] + 1 * PRICES['SKU-5']:.2f}"
    got = read(d, "total.txt")
    if got != want:
        return False, f"total.txt={got!r} want {want!r}"
    if read(d, "stamp.txt") != stamp_of(d / "total.txt"):
        return False, "stamp.txt does not match stamp.py output for total.txt"
    return True, "ok"


def c_restock(d: Path) -> tuple[bool, str]:
    want = "\n".join(sorted(s for s, n in STOCK.items() if n < 5))
    got = read(d, "restock.txt")
    if got != want:
        return False, f"restock.txt={got!r} want {want!r}"
    if read(d, "stamp.txt") != stamp_of(d / "restock.txt"):
        return False, "stamp mismatch"
    return True, "ok"


def c_fix_discount(d: Path) -> tuple[bool, str]:
    r = subprocess.run(
        ["python3", "-m", "unittest", "-q", "test_calc"], cwd=d, capture_output=True, text=True
    )
    if r.returncode != 0:
        return False, "unit tests fail: " + (r.stderr.strip().splitlines() or ["?"])[-1]
    if "SPRING" not in read(d, "calc.py") or str(DISCOUNTS["SPRING"]) not in read(d, "calc.py"):
        return False, "calc.py lacks SPRING discount"
    return True, "ok"


def c_config_port(d: Path) -> tuple[bool, str]:
    cfg = read(d, "config.ini")
    if f"port = {SETTINGS['listen_port']}" not in cfg:
        return False, f"config.ini port not set: {cfg!r}"
    if "host = 127.0.0.1" not in cfg:
        return False, "config.ini host line was changed"
    if read(d, "check.txt") != "CONFIG-OK":
        return False, f"check.txt={read(d, 'check.txt')!r}"
    return True, "ok"


def c_sort_expensive(d: Path) -> tuple[bool, str]:
    exp = {s for s, p in PRICES.items() if p > 20}
    for s in PRICES:
        in_exp = (d / "expensive" / f"{s}.txt").exists()
        in_root = (d / f"{s}.txt").exists()
        if (s in exp) != in_exp or (s in exp) == in_root:
            return False, f"{s} in wrong place"
    if read(d, "manifest.txt") != "\n".join(sorted(exp)):
        return False, f"manifest.txt={read(d, 'manifest.txt')!r}"
    return True, "ok"


def c_git_commit(d: Path) -> tuple[bool, str]:
    r = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=d, capture_output=True, text=True)
    if r.returncode != 0:
        return False, "no git commit"
    want = f"Price of SKU-3 is {PRICES['SKU-3']:.2f}"
    if r.stdout.strip() != want:
        return False, f"commit subject={r.stdout.strip()!r} want {want!r}"
    files = subprocess.run(
        ["git", "ls-files"], cwd=d, capture_output=True, text=True
    ).stdout.split()
    if "price.txt" not in files or read(d, "price.txt") != f"{PRICES['SKU-3']:.2f}":
        return False, "price.txt not committed with the price"
    return True, "ok"


def c_log_status(d: Path) -> tuple[bool, str]:
    errors = sum(1 for line in read(d, "app.log").splitlines() if " ERROR " in line)
    want = "ALERT" if errors > int(SETTINGS["max_errors"]) else "OK"
    got = read(d, "status.txt")
    if got != f"{want} {errors}":
        return False, f"status.txt={got!r} want {want} {errors!r}"
    return True, "ok"


def c_fill_prices(d: Path) -> tuple[bool, str]:
    try:
        data = json.loads(read(d, "products.json"))
    except json.JSONDecodeError:
        return False, "products.json is not valid JSON"
    for item in data:
        if item.get("price") != PRICES[item["sku"]]:
            return False, f"{item['sku']} price={item.get('price')}"
    if read(d, "validation.txt") != "VALID":
        return False, f"validation.txt={read(d, 'validation.txt')!r}"
    return True, "ok"


def c_report_table(d: Path) -> tuple[bool, str]:
    text = read(d, "report.md")
    for s in ("SKU-1", "SKU-2", "SKU-3"):
        row = next((ln for ln in text.splitlines() if ln.startswith(f"| {s} ")), "")
        cells = [c.strip() for c in row.strip("|").split("|")]
        if cells != [s, f"{PRICES[s]:.2f}", str(STOCK[s])]:
            return False, f"row for {s} wrong: {row!r}"
    lines = len((d / "report.md").read_text().splitlines())
    if read(d, "lines.txt") != str(lines):
        return False, f"lines.txt={read(d, 'lines.txt')!r} want {lines}"
    return True, "ok"


def c_fix_script(d: Path) -> tuple[bool, str]:
    r = subprocess.run(["sh", "greet.sh"], cwd=d, capture_output=True, text=True)
    if r.returncode != 0:
        return False, "greet.sh still fails"
    if read(d, "out.txt") != f"{SETTINGS['greeting']} world":
        return False, f"out.txt={read(d, 'out.txt')!r}"
    return True, "ok"


TASKS = [
    Task(
        "t01-order-total",
        "order.csv lists SKUs and quantities. Use the shop tool lookup_price to look up each "
        "SKU's unit price, compute the order total, and write it to total.txt as a number "
        "with exactly two decimals (nothing else). Then run `python3 stamp.py total.txt` "
        "and write its exact output to stamp.txt.",
        {"order.csv": "sku,qty\nSKU-1,3\nSKU-4,2\nSKU-5,1\n", "stamp.py": STAMP},
        c_order_total,
    ),
    Task(
        "t02-restock",
        "inventory.txt lists SKUs, one per line. Use the shop tool lookup_stock for each and write "
        "restock.txt containing only the SKUs with fewer than 5 units in stock, sorted, one per "
        "line. Then run `python3 stamp.py restock.txt` and write its exact output to stamp.txt.",
        {"inventory.txt": "SKU-1\nSKU-2\nSKU-3\nSKU-4\nSKU-5\n", "stamp.py": STAMP},
        c_restock,
    ),
    Task(
        "t03-fix-discount",
        "The unit tests in test_calc.py fail. Find the correct SPRING discount percentage with "
        "the shop tool get_discount, update calc.py so the tests pass, and run "
        "`python3 -m unittest test_calc` to confirm.",
        {
            "calc.py": "DISCOUNTS = {'VIP': 25}\n\n\ndef apply_discount(amount, code):\n"
            "    pct = DISCOUNTS.get(code, 0)\n    return round(amount * (100 - pct) / 100, 2)\n",
            "test_calc.py": "import unittest\nfrom calc import apply_discount\n\n\n"
            "class T(unittest.TestCase):\n    def test_spring(self):\n"
            "        self.assertEqual(apply_discount(200, 'SPRING'), 170.0)\n\n"
            "    def test_vip(self):\n        self.assertEqual(apply_discount(100, 'VIP'), 75.0)\n",
        },
        c_fix_discount,
    ),
    Task(
        "t04-config-port",
        "Set the port in config.ini to the value of the shop setting listen_port (use the shop "
        "tool get_setting). Change only the port line. Then run `python3 check_config.py` and "
        "write its exact output to check.txt.",
        {
            "config.ini": "[server]\nhost = 127.0.0.1\nport = 8080\n",
            "check_config.py": "import configparser\nc = configparser.ConfigParser()\n"
            "c.read('config.ini')\nprint('CONFIG-OK' if c['server']['port'] == '8443' "
            "else 'CONFIG-BAD')\n",
        },
        c_config_port,
    ),
    Task(
        "t05-sort-expensive",
        "There is one file per SKU (SKU-1.txt to SKU-5.txt). Use the shop tool lookup_price "
        "and move the files of SKUs priced above 20 into a new directory named expensive/ "
        "using shell commands. Then write manifest.txt listing the moved SKUs, sorted, "
        "one per line.",
        {f"{s}.txt": f"{s}\n" for s in PRICES},
        c_sort_expensive,
    ),
    Task(
        "t06-git-commit",
        "Initialise a git repository in this directory. Use the shop tool lookup_price to look up "
        "SKU-3, write the price with two decimals to price.txt, and commit price.txt with the "
        "commit message `Price of SKU-3 is <price>` (two decimals). Use author name 'Spike' and "
        "email 'spike@example.invalid' for the commit.",
        {"README.txt": "price workspace\n"},
        c_git_commit,
    ),
    Task(
        "t07-log-status",
        "Count the lines in app.log that contain ' ERROR ' using a shell command. Get the shop "
        "setting max_errors with get_setting. Write status.txt containing `ALERT <count>` if the "
        "count is greater than max_errors, otherwise `OK <count>`.",
        {
            "app.log": "".join(
                f"2026-11-11 10:{i:02d} {'ERROR' if i % 3 == 0 else 'INFO'} event {i}\n"
                for i in range(1, 16)
            )
        },
        c_log_status,
    ),
    Task(
        "t08-fill-prices",
        "products.json is a list of products whose price fields are null. Fill in each price "
        "with the shop tool lookup_price (a JSON number). Then run `python3 validate.py` and write "
        "its exact output to validation.txt.",
        {
            "products.json": json.dumps(
                [{"sku": s, "price": None} for s in ("SKU-2", "SKU-4", "SKU-5")], indent=2
            )
            + "\n",
            "validate.py": "import json\nd = json.load(open('products.json'))\n"
            "ok = all(isinstance(x['price'], (int, float)) for x in d)\n"
            "print('VALID' if ok else 'INVALID')\n",
        },
        c_fill_prices,
    ),
    Task(
        "t09-report-table",
        "Create report.md containing a Markdown table with columns sku, price, stock and one row "
        "each for SKU-1, SKU-2 and SKU-3 (in that order), using the shop tools lookup_price and "
        "lookup_stock. Write prices with two decimals. Rows must look like "
        "`| SKU-1 | 12.50 | 3 |`. Then run `wc -l < report.md` and write the number it "
        "prints to lines.txt.",
        {},
        c_report_table,
    ),
    Task(
        "t10-fix-script",
        "Running `sh greet.sh` fails. Run it, read the error, and fix greet.sh using the right "
        "value from the shop tool get_setting, so that `sh greet.sh` succeeds and writes "
        "out.txt. Then run it.",
        {
            "greet.sh": "GREETING=\"${GREETING:?set GREETING to the shop setting 'greeting'}\"\n"
            'echo "$GREETING world" > out.txt\n',
        },
        c_fix_script,
    ),
]


def setup(task: Task, d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for name, text in task.files.items():
        (d / name).write_text(text)
