#!/usr/bin/env python3
import asyncio, json, os, re, time, sys


async def login(page, username, password):
    url = "https://sistema.centraldaconsulta.com/painel/fazer-consulta/312"
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    if "fazer-consulta/312" not in page.url:
        # Redirected to login page
        await page.fill("input[type=\"text\"]", username)
        await page.fill("input[type=\"password\"]", password)
        await page.click("button[type=\"submit\"]")
        await page.wait_for_load_state("networkidle")
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
    return "fazer-consulta/312" in page.url


async def run_consultation(page, cpf):
    try:
        if "fazer-consulta/312" not in page.url:
            url = "https://sistema.centraldaconsulta.com/painel/fazer-consulta/312"
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
        cpf_input = page.locator("input[placeholder=\"000.000.000-00\"]")
        await cpf_input.fill("")
        await cpf_input.fill(cpf)
        await page.click("button[type=\"submit\"]:has-text(\"CONSULTAR\")")
        await page.wait_for_url("**/painel/historico/**", timeout=30000)
        await page.wait_for_load_state("networkidle")
        return await scrape_result(page)
    except Exception as e:
        print(f"  Error: {e}")
        return None


async def scrape_result(page):
    result = {}
    try:
        # Score
        score_el = await page.query_selector("text=SCORE")
        if score_el:
            parent = await score_el.evaluate_handle("el => el.parentElement")
            score_text = await page.evaluate("el => el.textContent", parent)
            sm = re.search(r"\d{1,3}", score_text.replace("SCORE", ""))
            if sm: result["score"] = int(sm.group())
        # Rating
        for rating in ["BOM", "REGULAR", "BAIXO", "RUIM", "OTIMO"]:
            el = await page.query_selector("text=" + rating)
            if el:
                result["rating"] = rating
                break
        # CPF from page
        cpf_text = await page.evaluate("""() => {""" +
            "const cells = document.querySelectorAll(\"td\");" +
            "for (const c of cells) {" +
            "const t = c.textContent.trim();" +
            "if (/^\\d{11}$/.test(t) || /^\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}$/.test(t)) return t;" +
            "} return null;}")
        if cpf_text:
            raw = re.sub(r"[^\d]", "", cpf_text)
            result["cpf_raw"] = raw
            result["cpf"] = f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"
        # Nome da Mae via JS
        mae = await page.evaluate("""() => {""" +
            "const cells = document.querySelectorAll(\"td\");" +
            "for (let i = 0; i < cells.length; i++) {" +
            "if (cells[i].textContent.includes(\"Nome da M\")) return cells[i+1]?.textContent?.trim() || null;" +
            "} return null;}")
        if mae: result["nome_mae"] = mae
        # Nascimento via JS
        nasc = await page.evaluate("""() => {""" +
            "const cells = document.querySelectorAll(\"td\");" +
            "for (let i = 0; i < cells.length; i++) {" +
            "if (cells[i].textContent.includes(\"Nascimento\")) return cells[i+1]?.textContent?.trim() || null;" +
            "} return null;}")
        if nasc: result["nascimento"] = nasc
        # Renda via JS
        renda = await page.evaluate("""() => {""" +
            "const cells = document.querySelectorAll(\"td\");" +
            "for (const c of cells) {" +
            "if (c.textContent.includes(\"RENDA PRESUMIDA\")) return c.textContent.trim();" +
            "} return null;}")
        if renda: result["renda_presumida"] = renda
        # Person name
        heading = await page.query_selector("h3, h4, h5")
        if heading: result["name"] = await heading.inner_text()
        # Rating from score if not found
        if "score" in result and "rating" not in result:
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
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        context = await browser.new_context(user_agent=ua)
        page = await context.new_page()
        print("Logging in...")
        logged_in = await login(page, username, password)
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
                await page.goto(url)
                await page.wait_for_load_state("networkidle")
                if "fazer-consulta/312" not in page.url:
                    await login(page, username, password)
        await browser.close()
    return results


def run_consultations_sync(cpf_list, username, password, output_dir="consultas"):
    return asyncio.run(run_batch(cpf_list, username, password, output_dir))


if __name__ == "__main__":
    username = os.environ.get("CONSULTA_USER", "")
    password = os.environ.get("CONSULTA_PASS", "")
    if not username or not password:
        print("Set CONSULTA_USER and CONSULTA_PASS env vars")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python3 consulta.py <CPF>")
        print("Example: CONSULTA_USER=39723326884 CONSULTA_PASS=Li302010! python3 consulta.py 087.381.466-57")
        sys.exit(1)
    cpf = sys.argv[1]
    print(f"Running consultation for CPF: {cpf}")
    results = run_consultations_sync([cpf], username, password)
    if results:
        print(json.dumps(results[0], indent=2, ensure_ascii=False))
    else:
        print("No results")
