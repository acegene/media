#!/usr/bin/env python3
# pokemon_tcg_code_inputter.py
# pylint: skip-file
import csv
import re
import time
from pathlib import Path
from typing import List
from typing import Optional
from typing import Tuple

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import sync_playwright

# ------------ config ------------
CODES_FILE = "codes.txt"
RESULTS_FILE = "redeem_results.csv"
BATCH_SIZE = 10

REDEEM_URLS = [
    "https://tcg.pokemon.com/en-us/tcgl/",
    "https://tcg.pokemon.com/en-gb/tcgl/",
]

TESTIDS = {
    "view": "code-redemption-view",
    "redeem_btn": "button-redeem",
    "clear_btn": "button-clear-table",
}

VIEW_SEL = f'section[data-testid="{TESTIDS["view"]}"]'
ROWS_SEL = f"{VIEW_SEL} tbody tr"
INPUT_ID_SEL = f"{VIEW_SEL} input#code, {VIEW_SEL} #code"
REDEEM_BTN_SEL = f'[data-testid="{TESTIDS["redeem_btn"]}"]'
CLEAR_BTN_SEL = f'[data-testid="{TESTIDS["clear_btn"]}"]'

REDEEM_TEXTS = [
    "Redeem Pokémon TCG Live code",
    "Redeem Now",
    "Redeem Code",
    "Redeem",
]

# Statuses that mean we should NOT click Redeem if *all* rows show only these
SKIP_STATUSES_RAW = {
    "You have already redeemed that code.",
    "That code has already been redeemed by someone else.",
}


# ------------ small utils ------------
def read_codes(path: str) -> List[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Could not find {path}")
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def chunks(seq: List[str], size: int) -> List[List[str]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def human_pause(s=0.5):
    time.sleep(s)


def dismiss_overlays(page: Page):
    for pat in [r"accept", r"agree", r"ok", r"got it", r"continue", r"confirm", r"allow", r"close"]:
        try:
            page.get_by_role("button", name=re.compile(pat, re.I)).click(timeout=600)
        except:
            pass
    for sel in [
        "[id*='cookie'] button",
        "[class*='cookie'] button",
        "[id*='consent'] button",
        "[class*='consent'] button",
        "button[aria-label*='close' i]",
    ]:
        try:
            page.locator(sel).first.click(timeout=600)
        except:
            pass


def click_redeemish(page: Page) -> bool:
    for label in REDEEM_TEXTS:
        try:
            page.get_by_role("link", name=re.compile(re.escape(label), re.I)).first.click(timeout=1200)
            return True
        except:
            pass
        try:
            page.get_by_role("button", name=re.compile(re.escape(label), re.I)).first.click(timeout=1200)
            return True
        except:
            pass
    try:
        page.get_by_text(re.compile(r"redeem", re.I)).first.click(timeout=1200)
        return True
    except:
        pass
    return False


# ------------ navigation that auto-finds the real redeem view ------------
def open_landing(page: Page):
    for url in REDEEM_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            human_pause(1.0)
            dismiss_overlays(page)
            return
        except Exception:
            continue


def try_open_redeem(context, page: Page):
    dismiss_overlays(page)
    with context.expect_event("page", timeout=3000) as new_tab:
        clicked = click_redeemish(page)
        if not clicked:
            pass
    try:
        p = new_tab.value
        p.wait_for_load_state("domcontentloaded", timeout=15000)
        p.bring_to_front()
    except Exception:
        pass


def find_tab_with_redeem_view(context, timeout_sec: int = 120) -> Optional[Page]:
    deadline = time.time() + timeout_sec
    last_urls = None
    while time.time() < deadline:
        pages = context.pages
        urls = [p.url for p in pages]
        if urls != last_urls:
            print("[debug] open tabs:", urls)
            last_urls = urls
        for p in pages:
            try:
                dismiss_overlays(p)
                if p.locator(VIEW_SEL).count() or p.locator(INPUT_ID_SEL).count():
                    print("[debug] found redeem view on:", p.url)
                    p.bring_to_front()
                    p.wait_for_load_state("domcontentloaded", timeout=15000)
                    return p
                for fr in p.frames:
                    if fr.locator(VIEW_SEL).count() or fr.locator(INPUT_ID_SEL).count():
                        print("[debug] found redeem view in frame on:", p.url)
                        p.bring_to_front()
                        p.wait_for_load_state("domcontentloaded", timeout=15000)
                        return p
            except Exception:
                continue
        human_pause(0.5)
    return None


# ------------ redeem-page helpers ------------
def find_redeem_input(page: Page) -> Optional[Locator]:
    box = page.locator(INPUT_ID_SEL)
    if box.count():
        return box.first
    any_tb = page.locator(f'{VIEW_SEL} input[type="text"], {VIEW_SEL} textarea, {VIEW_SEL} [contenteditable="true"]')
    if any_tb.count():
        return any_tb.first
    for fr in page.frames:
        box = fr.locator(INPUT_ID_SEL)
        if box.count():
            return box.first
        any_tb = fr.locator(f'{VIEW_SEL} input[type="text"], {VIEW_SEL} textarea, {VIEW_SEL} [contenteditable="true"]')
        if any_tb.count():
            return any_tb.first
    return None


def wait_for_row_increase(page: Page, before_count: int, timeout_ms: int = 6000):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        try:
            c = page.locator(ROWS_SEL).count()
            if c > before_count:
                return True
        except:
            pass
        time.sleep(0.15)
    return False


def add_code(page: Page, input_box: Locator, code: str):
    rows_before = page.locator(ROWS_SEL).count()
    input_box.click()
    try:
        input_box.fill("")
    except:
        pass
    input_box.type(code, delay=35)
    try:
        input_box.press("Enter")
    except:
        pass
    wait_for_row_increase(page, rows_before)


def scrape_table_statuses(page: Page) -> List[Tuple[str, str]]:
    rows = page.locator(ROWS_SEL)
    n = rows.count()
    out: List[Tuple[str, str]] = []
    for i in range(n):
        tds = rows.nth(i).locator("td")
        try:
            code = tds.nth(0).inner_text().strip()
        except:
            code = ""
        try:
            status = tds.nth(1).inner_text().strip()
        except:
            status = ""
        if code or status:
            out.append((code, status))
    return out


def click_redeem(page: Page):
    btn = page.locator(REDEEM_BTN_SEL).first
    btn.wait_for(state="visible", timeout=15000)
    if not btn.is_enabled():
        page.wait_for_timeout(500)
    btn.click()


def click_clear(page: Page):
    clr = page.locator(CLEAR_BTN_SEL).first
    try:
        clr.wait_for(state="visible", timeout=8000)
        clr.click()
    except:
        try:
            page.get_by_role("button", name=re.compile(r"clear|reset", re.I)).click(timeout=1500)
        except:
            pass


# ------------ skipping logic ------------
def _normalize_status(s: str) -> str:
    # lower, strip, collapse spaces, drop trailing punctuation
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s']+$", "", s)  # remove trailing punctuation (., !, etc.)
    return s


SKIP_STATUSES_NORM = {_normalize_status(s) for s in SKIP_STATUSES_RAW}


def should_skip_redeem(table_status: List[Tuple[str, str]]) -> bool:
    """Return True iff there is at least 1 row AND every row's status is one of the two 'already redeemed' messages."""
    if not table_status:
        return False
    statuses = [_normalize_status(s) for _, s in table_status if s.strip()]
    if not statuses:
        return False
    return all(st in SKIP_STATUSES_NORM for st in statuses)


# ------------ main ------------
def main():
    all_codes = read_codes(CODES_FILE)
    batches = chunks(all_codes, BATCH_SIZE)

    write_header = not Path(RESULTS_FILE).exists()
    out = open(RESULTS_FILE, "a", newline="", encoding="utf-8")
    writer = csv.writer(out)
    if write_header:
        writer.writerow(["code", "status_before_redeem", "timestamp"])

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(Path(".playwright").absolute()),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.new_page()
        open_landing(page)
        try_open_redeem(context, page)

        redeem_page = find_tab_with_redeem_view(context, timeout_sec=120)
        if not redeem_page:
            raise RuntimeError("Could not locate the Redeem UI in any tab. Log in and try again.")

        input_box = find_redeem_input(redeem_page)
        if not input_box:
            raise RuntimeError("Redeem input not found. Selectors may have changed.")

        for bi, batch in enumerate(batches, start=1):
            print(f"\n=== Batch {bi}/{len(batches)} ({len(batch)} codes) ===")
            for code in batch:
                add_code(redeem_page, input_box, code)
                human_pause(0.25)

            # Scrape BEFORE clicking Redeem
            table_status = scrape_table_statuses(redeem_page)
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            for code, status in table_status:
                if code or status:
                    writer.writerow([code, status, ts])
                    print(f"table: {code} -> {status}")
            out.flush()

            # NEW: Skip Redeem if every row is an "already redeemed" message
            if should_skip_redeem(table_status):
                print("[info] All rows are already-redeemed statuses — skipping Redeem click.")
            else:
                try:
                    click_redeem(redeem_page)
                except Exception as e:
                    print(f"[warn] Could not click Redeem automatically: {e}. Click it manually, then press Enter.")
                    input()

                human_pause(2.0)

            # Clear table and proceed
            click_clear(redeem_page)
            human_pause(1.0)

        print(f"\nDone. Results saved to {RESULTS_FILE}")
        try:
            context.close()
        except:
            pass
    out.close()


if __name__ == "__main__":
    main()
