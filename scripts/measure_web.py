"""Before/after numbers for the 10,000-row screen (README, "Performance evidence").

    make up && python3 scripts/measure_web.py            # needs: pip install playwright
    python3 scripts/measure_web.py --browser chromium     # if you ran `playwright install chromium`

Loads /bench.html (the real FollowUpTable with 10,000 invented rows) in Chrome with 4x CPU
throttling, standing in for a 6-10 year old clinic PC, and reports the median of 5 cold loads for:
  naive   - every row in the DOM (the "before")
  virtual - row virtualisation, as shipped (the "after")
"""
import argparse
import statistics

from playwright.sync_api import sync_playwright

URL = "http://localhost:5173/bench.html?mode={mode}"
RUNS = 5


def measure(browser, mode: str) -> dict:
    page = browser.new_page(viewport={"width": 1366, "height": 768})
    cdp = page.context.new_cdp_session(page)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    cdp.send("Performance.enable")
    page.goto(URL.format(mode=mode))
    page.wait_for_function("window.__bench !== undefined", timeout=120_000)
    result = page.evaluate("window.__bench")
    metrics = {m["name"]: m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
    # Scrolling cost: time to scroll to the middle and paint.
    scroll_ms = page.evaluate("""() => new Promise(resolve => {
        const el = document.querySelector('.table-scroll');
        const t = performance.now();
        el.scrollTop = el.scrollHeight / 2;
        requestAnimationFrame(() => requestAnimationFrame(() => resolve(performance.now() - t)));
    })""")
    page.close()
    return {**result, "heapMb": metrics["JSHeapUsedSize"] / 1_048_576, "scrollMs": scroll_ms}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", choices=["chrome", "chromium"], default="chrome")
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome" if args.browser == "chrome" else None)
        print(f"Browser: {browser.version}, CPU throttled 4x, 10,000 rows, median of {RUNS} cold loads\n")
        print(f"{'':10}{'first paint':>14}{'DOM nodes':>12}{'JS heap':>11}{'scroll+paint':>15}")
        for mode in ("naive", "virtual"):
            runs = [measure(browser, mode) for _ in range(RUNS)]
            med = {k: statistics.median(r[k] for r in runs) for k in ("renderMs", "domNodes", "heapMb", "scrollMs")}
            print(f"{mode:10}{med['renderMs']:>11.0f} ms{med['domNodes']:>12,.0f}{med['heapMb']:>8.1f} MB"
                  f"{med['scrollMs']:>12.0f} ms")
        browser.close()


if __name__ == "__main__":
    main()
