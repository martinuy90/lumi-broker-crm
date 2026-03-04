#!/usr/bin/env python3
"""
Lumi CRM Auto-Updater — Main Orchestrator
Runs hourly via GitHub Actions. Zero human intervention.

Flow:
1. Load existing data files (scores, pendente, brokers, config)
2. Fetch fresh CSVs from Google Sheets
3. Process leads, detect changes, discover new CPFs
4. Run credit consultations for new CPFs (via Playwright)
5. Rebuild dashboard HTML
6. Save updated data files
"""

import json
import os
import sys
import re
from datetime import datetime

# Add current dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_data import (
    fetch_csv, process_leads, find_new_cpfs,
    detect_data_changes, validate_cpf, normalize_cpf, compute_kpis,
    count_dados_completos, GIDS
)
from generate_html import generate_html

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUTPUT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


def load_json(filename):
    """Load a JSON file from the data directory."""
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_json(filename, data):
    """Save data to a JSON file in the data directory."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Saved {path}")


def increment_version(current_version):
    """Increment minor version: 7.0 -> 7.1, 7.9 -> 7.10"""
    parts = current_version.split('.')
    major = int(parts[0])
    minor = int(parts[1]) + 1
    return f"{major}.{minor}"


def restore_cookies_from_env():
    """Restore session cookies from CONSULTA_COOKIES env var (GitHub secret).
    This allows headless consultations without interactive login."""
    cookies_json = os.environ.get('CONSULTA_COOKIES', '')
    if not cookies_json:
        return False
    try:
        cookie_file = os.path.join(DATA_DIR, "session_cookies.json")
        # Only write if file doesn't exist or is empty
        if not os.path.exists(cookie_file) or os.path.getsize(cookie_file) < 10:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(cookie_file, 'w') as f:
                f.write(cookies_json)
            cookies = json.loads(cookies_json)
            print(f"  Restored {len(cookies)} cookies from CONSULTA_COOKIES secret")
            return True
        else:
            print(f"  Cookie file already exists, using local version")
            return True
    except Exception as e:
        print(f"  WARNING: Failed to restore cookies: {e}")
        return False


def run_credit_consultations(new_cpfs, config):
    """Run credit consultations for new CPFs via Playwright.
    Returns list of result dicts."""
    if not new_cpfs:
        print("  No new CPFs to consult.")
        return []

    username = os.environ.get('CONSULTA_USER', '')
    password = os.environ.get('CONSULTA_PASS', '')

    if not username or not password:
        print("  WARNING: CONSULTA_USER/CONSULTA_PASS not set. Skipping consultations.")
        return []

    # Restore session cookies from environment (for GitHub Actions)
    restore_cookies_from_env()

    try:
        from consulta import run_consultations_sync
    except ImportError as e:
        print(f"  WARNING: Could not import consulta module: {e}")
        print("  Skipping credit consultations.")
        return []

    cpf_list = [entry['cpf'] for entry in new_cpfs if validate_cpf(entry['cpf'])]
    invalid = [entry for entry in new_cpfs if not validate_cpf(entry['cpf'])]

    if invalid:
        print(f"  Skipping {len(invalid)} invalid CPFs: {[e['cpf'] for e in invalid]}")

    if not cpf_list:
        print("  No valid CPFs to consult.")
        return []

    print(f"  Running {len(cpf_list)} consultations...")
    results = run_consultations_sync(cpf_list, username, password)

    successful = [r for r in results if 'score' in r and 'error' not in r]
    failed = [r for r in results if 'error' in r]

    print(f"  Completed: {len(successful)} successful, {len(failed)} failed")
    return results


def build_summary(changes, new_scores, new_cpfs, new_leads_count, version):
    """Build the summary text for the dashboard header."""
    parts = [f"<b>Resumo v{version}:</b>"]

    if new_leads_count > 0:
        parts.append(f"+{new_leads_count} novos leads.")

    if new_scores:
        score_texts = []
        for s in new_scores[:3]:  # Max 3 in summary
            name = s.get('name', '?').split()[0]  # First name only
            score_texts.append(f"<b>{name} {s['score']} {s['rating']}</b>")
        parts.append(f"{len(new_scores)} novos scores: {', '.join(score_texts)}.")

    if new_cpfs:
        parts.append(f"{len(new_cpfs)} novos CPFs descobertos.")

    if changes:
        parts.append(f"{len(changes)} leads com dados atualizados.")

    # Check for ready leads
    # (computed later from KPIs)

    return " ".join(parts)


def main():
    """Main orchestrator function."""
    print("=" * 60)
    print(f"Lumi CRM Auto-Update — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    # ── Step 1: Load existing data ──
    print("\n[1/6] Loading data files...")
    scores = load_json("scores.json") or []
    pendente = load_json("pendente.json") or []
    brokers = load_json("brokers.json") or {"approved": [], "rejected": [], "invalid_cpf": []}
    config = load_json("config.json") or {}

    current_version = config.get("version", "7.0")
    tracking = config.get("tracking", {})
    last_leads_row = tracking.get("last_leads_row", 0)
    last_historico_row = tracking.get("last_historico_row", 0)

    print(f"  Loaded: {len(scores)} scores, {len(pendente)} pendente, "
          f"v{current_version}, last_leads={last_leads_row}, last_hist={last_historico_row}")

    # ── Step 2: Fetch fresh CSVs ──
    print("\n[2/6] Fetching Google Sheets CSVs...")
    dashboard_dados_rows = []
    try:
        leads_rows = fetch_csv(GIDS["leads"])
        historico_rows = fetch_csv(GIDS["historico"])
        dashboard_dados_rows = fetch_csv(GIDS["dashboard_dados"])
        print(f"  Fetched: {len(leads_rows)} leads, {len(historico_rows)} historico, {len(dashboard_dados_rows)} dashboard_dados")
    except Exception as e:
        print(f"  ERROR fetching CSVs: {e}")
        print("  Continuing with existing data...")
        leads_rows = []
        historico_rows = []

    # ── Step 3: Process leads + detect changes ──
    print("\n[3/6] Processing leads and detecting changes...")
    new_leads_count = 0
    changes = []
    new_cpf_discoveries = []

    if leads_rows:
        leads = process_leads(leads_rows)
        total_leads = len(leads)
        new_leads_count = max(0, total_leads - (last_leads_row or total_leads))
        print(f"  Total leads (excl. cofounders): {total_leads}")
        if new_leads_count > 0:
            print(f"  New leads since last run: {new_leads_count}")

        # Build set of known CPFs
        known_cpfs = set()
        for s in scores:
            known_cpfs.add(re.sub(r'[^\d]', '', s.get('cpf', '')))
        for p in pendente:
            known_cpfs.add(re.sub(r'[^\d]', '', p.get('cpf', '')))
        for b in brokers.get('rejected', []):
            known_cpfs.add(re.sub(r'[^\d]', '', b.get('cpf', '')))
        for b in brokers.get('invalid_cpf', []):
            known_cpfs.add(re.sub(r'[^\d]', '', b.get('cpf', '')))
        known_cpfs.discard('')

        # Detect data changes for existing leads
        # (compare leads CSV fields with what we have)
        # changes = detect_data_changes(leads, known_data)

        # Search historico for new CPFs
        if historico_rows:
            new_cpf_discoveries = find_new_cpfs(historico_rows, known_cpfs, last_historico_row)
            if new_cpf_discoveries:
                print(f"  Found {len(new_cpf_discoveries)} new CPFs in historico!")
                for disc in new_cpf_discoveries:
                    print(f"    CPF: {disc['cpf']} (phone: {disc.get('phone', '?')})")
            else:
                print("  No new CPFs found in historico.")

        # Update tracking
        tracking["last_leads_row"] = total_leads
        tracking["last_historico_row"] = len(historico_rows)
    else:
        total_leads = tracking.get("last_leads_row", 249)

    # ── Step 4: Run credit consultations for new CPFs ──
    print("\n[4/6] Credit consultations...")
    new_scores = []

    if new_cpf_discoveries:
        # Prepare CPF list for consultation
        cpfs_to_consult = []
        for disc in new_cpf_discoveries:
            cpf = disc['cpf']
            if validate_cpf(cpf):
                cpfs_to_consult.append(disc)
            else:
                print(f"  Invalid CPF {cpf} — adding to invalid list")
                brokers["invalid_cpf"].append({
                    "name": disc.get("name", "?"),
                    "cpf": normalize_cpf(cpf) if len(re.sub(r'[^\d]', '', cpf)) == 11 else cpf
                })

        consultation_results = run_credit_consultations(cpfs_to_consult, config)

        for result in consultation_results:
            if 'score' in result and 'error' not in result:
                # Add to scores
                new_entry = {
                    "name": result.get("name", "?"),
                    "cpf": result.get("cpf", normalize_cpf(result.get("input_cpf", ""))),
                    "score": result["score"],
                    "rating": result.get("rating", "?"),
                    "renda": "—",
                    "falta": "Falta: Dados pessoais + imóvel",
                    "status": "Score baixo" if result["score"] < 400 else "Coletar dados",
                    "row_class": "ry" if result["score"] >= 400 else ("ro" if result["score"] >= 277 else "rr")
                }
                scores.append(new_entry)
                new_scores.append(result)

                # Remove from pendente if present
                cpf_raw = re.sub(r'[^\d]', '', result.get("cpf", ""))
                pendente = [p for p in pendente if re.sub(r'[^\d]', '', p.get('cpf', '')) != cpf_raw]

                print(f"  NEW SCORE: {result.get('name', '?')} → {result['score']} {result.get('rating', '?')}")
            elif 'error' not in result:
                # No score but no error — add to pendente
                pass
    else:
        print("  No new CPFs to consult.")

    # Sort scores by score value (highest first)
    scores.sort(key=lambda x: x.get('score', 0), reverse=True)

    # ── Step 5: Rebuild dashboard ──
    print("\n[5/6] Generating dashboard HTML...")
    new_version = increment_version(current_version)

    # Compute KPIs
    n_dados_completos = count_dados_completos(dashboard_dados_rows)
    kpis = compute_kpis(scores, pendente, brokers, total_leads, dados_completos=n_dados_completos)
    print(f"  KPIs: {json.dumps(kpis)}")

    # Build summary
    summary = build_summary(changes, new_scores, new_cpf_discoveries, new_leads_count, new_version)
    if not new_scores and not new_cpf_discoveries and new_leads_count == 0:
        summary = f"<b>Resumo v{new_version}:</b> Atualização automática. Sem alterações detectadas."

    # Generate HTML
    html = generate_html(scores, pendente, brokers, config, kpis, new_version, summary)

    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Generated: {OUTPUT_HTML} ({len(html)} bytes)")

    # ── Step 6: Save updated data ──
    print("\n[6/6] Saving data files...")
    config["version"] = new_version
    config["tracking"] = tracking
    config["last_update"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    save_json("scores.json", scores)
    save_json("pendente.json", pendente)
    save_json("brokers.json", brokers)
    save_json("config.json", config)

    # ── Summary ──
    print("\n" + "=" * 60)
    print(f"UPDATE COMPLETE — v{new_version}")
    print(f"  Total leads: {total_leads}")
    print(f"  New leads: {new_leads_count}")
    print(f"  New CPFs discovered: {len(new_cpf_discoveries)}")
    print(f"  New scores: {len(new_scores)}")
    print(f"  Data changes: {len(changes)}")
    print(f"  KPIs: {kpis}")
    print("=" * 60)

    return {
        "version": new_version,
        "new_leads": new_leads_count,
        "new_cpfs": len(new_cpf_discoveries),
        "new_scores": len(new_scores),
        "changes": len(changes),
        "kpis": kpis
    }


if __name__ == '__main__':
    result = main()
    if result:
        print(f"\nDone! Version {result['version']} generated.")
