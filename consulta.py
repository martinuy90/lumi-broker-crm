#!/usr/bin/env python3
import asyncio, json, os, re, time, sys

COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "session_cookies.json")


async def save_cookies(context):
    """Save browser cookies to file for reuse."""
    cookies = await context.cookies()
    os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
    with open(COOKIE_FILE, 'w') as f:
        json.dump(cookies, f)
    print(f"  Saved {len(cookies)} cookies to {COOKIE_FILE}")


async def load_cookies(context):
    """Load saved cookies into browser context."""
    if not os.path.exists(COOKIE_FILE):
        return False
    try:
        with open(COOKIE_FILE, 'r') as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
        print(f"  Loaded {len(cookies)} saved cookies")
        return True
    except Exception as e:
        print(f"  Could not load cookies: {e}")
        return False


async def login(page, username, password, context=None):
    url = "https://sistema.centraldaconsulta.com/painel/fazer-consulta/312"

    # Try saved cookies first
    if context:
        loaded = await load_cookies(context)
        if loaded:
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            if "fazer-consulta/312" in page.url:
                print("  Session restored from cookies!")
                return True
            print("  Saved cookies expired, need fresh login.")

    # Navigate to form (will redirect to login if not authenticated)
    await page.goto(url, timeout=30000)
    await page.wait_for_load_state("domcontentloaded", timeout=15000)
    if "fazer-consulta/312" in page.url:
        return True

    # Login page — fill credentials
    print(f"  Login page: {page.url}")
    await page.wait_for_selector("input#email", timeout=10000)
    await page.fill("input#email", username)
    await page.fill("input#password", password)

    # Click ACESSAR (may fail due to reCAPTCHA in headless mode)
    try:
        async with page.expect_navigation(timeout=15000):
            await page.click("button[type=submit]:has-text('ACESSAR')")
    except Exception as e:
        print(f"  Login navigation error: {e}")

    await page.wait_for_load_state("domcontentloaded", timeout=15000)

    if "/login" in page.url:
        # Check for CAPTCHA error
        body = await page.inner_text("body")
        if "captcha" in body.lower():
            print("  LOGIN BLOCKED BY CAPTCHA — run 'python3 consulta.py --save-session' locally to authenticate")
        else:
            print(f"  Login failed. Page: {page.url}")
        return False

    # Success — save cookies for future runs
    if context:
        await save_cookies(context)

    if "fazer-consulta/312" not in page.url:
        await page.goto(url, timeout=30000)
        await page.wait_for_load_state("domcontentloaded", timeout=15000)

    return "fazer-consulta/312" in page.url


async def interactive_login(username, password):
    """Open a visible browser for manual CAPTCHA solving, then save cookies."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://sistema.centraldaconsulta.com/login", timeout=30000)
        await page.wait_for_load_state("domcontentloaded")

        # Pre-fill credentials
        await page.fill("input#email", username)
        await page.fill("input#password", password)

        print("\n  >>> Browser opened. Solve the CAPTCHA and click ACESSAR <<<")
        print("  >>> Waiting for login to complete...\n")

        # Wait for navigation away from login page (user solves CAPTCHA)
        try:
            await page.wait_for_url("**/painel/**", timeout=120000)
            print(f"  Login successful! URL: {page.url}")
            await save_cookies(context)
            print("  Session saved. Future runs will reuse this session.")
        except Exception as e:
            print(f"  Timeout waiting for login: {e}")

        await browser.close()


async def run_consultation(page, cpf):
    """Run a single CPF credit consultation.

    The consultation form at /painel/fazer-consulta/312 has:
    - Form action: POST /painel/ExecutarConsulta
    - Hidden inputs: _token (CSRF), produtoID (312), metodo (scoremais)
    - CPF input: input#cpf
    - Submit button: #btnConsultarPF (disabled until CPF validates)

    The button's jQuery click handler validates CPF then lets the form submit.
    We type the CPF via keyboard to trigger the site's own formatting + validation,
    then fall back to direct form submission if the button stays disabled.
    """
    try:
        url = "https://sistema.centraldaconsulta.com/painel/fazer-consulta/312"
        if "fazer-consulta/312" not in page.url:
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

        # Clean CPF to raw digits
        raw = re.sub(r"[^\d]", "", cpf)
        if len(raw) != 11:
            print(f"  Invalid CPF length: {raw}")
            return None
        formatted = f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"

        # Method 1: Type CPF via keyboard (triggers real input events + site's formatarCPF)
        cpf_input = page.locator("input#cpf")
        await cpf_input.click()
        # Clear existing value
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        # Type raw digits — the site's input listener auto-formats to XXX.XXX.XXX-XX
        await cpf_input.type(raw, delay=30)
        await asyncio.sleep(0.5)

        # Check if button got enabled naturally
        btn_disabled = await page.evaluate("document.getElementById('btnConsultarPF').disabled")
        print(f"  Button disabled after typing: {btn_disabled}")

        if not btn_disabled:
            # Button enabled — click it normally (triggers jQuery handler + form submit)
            async with page.expect_navigation(timeout=30000):
                await page.click("#btnConsultarPF")
        else:
            # Button still disabled — set value directly and submit form via JS
            print(f"  Falling back to direct form submission")
            await page.evaluate(f"""() => {{
                // Set CPF value in the correct format
                document.getElementById('cpf').value = '{formatted}';
                // Find the consultation form (has produtoID input, not the search form)
                const forms = document.querySelectorAll('form');
                for (const f of forms) {{
                    if (f.querySelector('[name="produtoID"]')) {{
                        f.submit();
                        return;
                    }}
                }}
            }}""")
            # Wait for navigation
            await page.wait_for_url(lambda url: "historico" in url or "ExecutarConsulta" in url, timeout=30000)

        # Wait for result page to load
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # Check if we ended up on the result page
        if "historico" in page.url:
            return await scrape_result(page)
        else:
            print(f"  Unexpected URL after submission: {page.url}")
            # Maybe the server redirected somewhere else — check page content
            body = await page.evaluate("() => document.body?.innerText?.substring(0, 500)")
            print(f"  Page content: {body[:200] if body else '(empty)'}")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


async def scrape_result(page):
    """Scrape consultation result from /painel/historico/{id}.

    Page structure:
    - H1: "312 - SCORE Positivo" (312 = product ID, NOT the score!)
    - H3 "SCORE" with child <span> containing the actual score number
    - H3 with person name (e.g., "ADRIANO MOREIRA")
    - SVG gauge with all rating labels (RUIM, BAIXO, REGULAR, BOM) — DO NOT use these
    - Table with consultation details:
      Row: "Nome da Mãe:" | value
      Row: "Data de Nascimento:" | value
      Row headers: "Score:" | "Probabilidade:" | "Situação:" | "Classificação:" | "Texto:"
      Row values:  "202"  | "03400"          | "Ruim"      | "Risco Alto..."   | "..."
    - Renda presumida text
    """
    result = {}
    try:
        # All data extracted in one JS call for efficiency
        data = await page.evaluate("""() => {
            const out = {};

            // Score: find H3 starting with "SCORE" → child span with number
            const h3s = document.querySelectorAll('h3');
            for (const h of h3s) {
                if (h.textContent.trim().startsWith('SCORE')) {
                    const span = h.querySelector('span');
                    if (span) {
                        const num = parseInt(span.textContent.trim());
                        if (!isNaN(num) && num >= 0 && num <= 999) out.score = num;
                    }
                    break;
                }
            }

            // Fallback: score from table "Score:" header row
            if (!out.score && out.score !== 0) {
                const cells = document.querySelectorAll('td');
                for (let i = 0; i < cells.length; i++) {
                    if (cells[i].textContent.trim() === 'Score:') {
                        // Values are in the next row, offset by number of header columns
                        // Find how many header cells follow
                        let headerCount = 1;
                        for (let j = i + 1; j < cells.length; j++) {
                            if (cells[j].textContent.trim().endsWith(':')) headerCount++;
                            else break;
                        }
                        const valCell = cells[i + headerCount];
                        if (valCell) {
                            const num = parseInt(valCell.textContent.trim());
                            if (!isNaN(num)) out.score = num;
                        }
                        break;
                    }
                }
            }

            // Person name: H3 that is NOT "SCORE" heading, contains all-uppercase name
            for (const h of h3s) {
                const t = h.textContent.trim();
                if (t && !t.startsWith('SCORE') && /^[A-ZÀÁÂÃÉÊÍÓÔÕÚÇ ]+$/.test(t) && t.length > 3) {
                    out.name = t;
                    break;
                }
            }

            // Table data: iterate td cells for key-value pairs
            const cells = document.querySelectorAll('td');
            for (let i = 0; i < cells.length; i++) {
                const label = cells[i].textContent.trim();
                const nextCell = cells[i + 1];
                if (!nextCell) continue;
                const value = nextCell.textContent.trim();

                if (label.includes('Nome da M')) out.nome_mae = value;
                else if (label.includes('Nascimento')) out.nascimento = value;
            }

            // CPF: find 11-digit number in table cells
            for (const c of cells) {
                const t = c.textContent.trim();
                if (/^\\d{11}$/.test(t)) { out.cpf_raw = t; break; }
            }

            // Renda presumida
            for (const c of cells) {
                const t = c.textContent.trim();
                if (t.includes('RENDA PRESUMIDA')) { out.renda_presumida = t; break; }
            }

            return out;
        }""")

        if data:
            result.update(data)

        # Format CPF
        if "cpf_raw" in result:
            raw = result["cpf_raw"]
            result["cpf"] = f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"

        # Calculate rating from score (don't trust page ratings — SVG gauge shows ALL labels)
        if "score" in result:
            s = result["score"]
            if s >= 600: result["rating"] = "BOM"
            elif s >= 400: result["rating"] = "REGULAR"
            elif s >= 200: result["rating"] = "BAIXO"
            else: result["rating"] = "RUIM"

    except Exception as e:
        print(f"  Error scraping: {e}")
    return result


async def run_batch(cpf_list, username, password, output_dir="consultas"):
    from playwright.async_api import async_playwright
    os.makedirs(output_dir, exist_ok=True)
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        context = await browser.new_context(user_agent=ua)
        page = await context.new_page()
        print("Logging in...")
        logged_in = await login(page, username, password, context)
        if not logged_in:
            print("Login failed!")
            await browser.close()
            return results
        print("Login successful!")
        for i, cpf in enumerate(cpf_list):
            print(f"Consulting: {cpf}")
            result = await run_consultation(page, cpf)
            if result:
                result["input_cpf"] = cpf
                results.append(result)
                print(f"  Score: {result.get('score', '?')}")
            else:
                print("  Retrying...")
                await asyncio.sleep(2)
                result = await run_consultation(page, cpf)
                if result:
                    result["input_cpf"] = cpf
                    results.append(result)
            # Rate limit + navigate back
            if i < len(cpf_list) - 1:
                await asyncio.sleep(3)
                url = "https://sistema.centraldaconsulta.com/painel/fazer-consulta/312"
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                if "fazer-consulta/312" not in page.url:
                    await login(page, username, password)
        await browser.close()
    return results


def run_consultations_sync(cpf_list, username, password, output_dir="consultas"):
    return asyncio.run(run_batch(cpf_list, username, password, output_dir))


if __name__ == "__main__":
    username = os.environ.get("CONSULTA_USER", "39723326884")
    password = os.environ.get("CONSULTA_PASS", "Li302010!")

    if len(sys.argv) >= 2 and sys.argv[1] == "--save-session":
        print("Opening browser for manual login (solve CAPTCHA)...")
        asyncio.run(interactive_login(username, password))
    elif len(sys.argv) >= 2:
        cpf = sys.argv[1]
        print(f"Running consultation for CPF: {cpf}")
        results = run_consultations_sync([cpf], username, password)
        if results:
            print(json.dumps(results[0], indent=2, ensure_ascii=False))
        else:
            print("No results")
    else:
        print("Usage:")
        print("  python3 consulta.py --save-session   # Login manually, save cookies")
        print("  python3 consulta.py <CPF>            # Run consultation")
        print("  python3 consulta.py 087.381.466-57   # Example")
