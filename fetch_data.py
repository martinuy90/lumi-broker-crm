#!/usr/bin/env python3
"""
Lumi CRM — Google Sheets CSV Fetcher & Data Processor
Downloads leads, historico, dashboard_dados from Google Sheets.
Processes leads, discovers new CPFs, detects data changes.
"""

import csv
import io
import re
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime

SHEET_ID = "1AuW-FQKAOIpb-BAkZqmbfejeTn98qhgCm8HlhWH5Cgo"
GIDS = {
    "leads": "0",
    "dashboard_dados": "739841676",
    "historico": "2069959500"
}

BASE_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid="

COFOUNDER_NAMES = [
    "Martin Coulthurst", "Bernardo Precht", "Elisa Pereira",
    "Martin Cultru", "Bernardo Luiz Campanario Precht"
]
COFOUNDER_PHONES = ["59899143298", "5521964436960"]

# CPF pattern: 3.3.3-2 with optional dots/dash, or raw 11 digits
CPF_PATTERN = re.compile(r'(\d{3}\.?\d{3}\.?\d{3}-?\d{2})')
CPF_RAW_PATTERN = re.compile(r'\b(\d{11})\b')


def fetch_csv(gid, max_retries=3):
    """Download CSV from Google Sheets. Returns list of dicts."""
    url = BASE_URL + gid
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(data))
            rows = list(reader)
            return rows
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            wait = 2 ** attempt
            print(f"  Fetch error (attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise Exception(f"Failed to fetch CSV after {max_retries} attempts (gid={gid})")


def fetch_all_csvs():
    """Fetch all 3 CSVs. Returns dict of {name: rows}."""
    result = {}
    for name, gid in GIDS.items():
        print(f"  Fetching {name}...", end=" ")
        rows = fetch_csv(gid)
        print(f"{len(rows)} rows")
        result[name] = rows
    return result


def validate_cpf(cpf_str):
    """Brazilian CPF validation (modulo 11 algorithm).
    Returns True if valid, False otherwise."""
    cpf = re.sub(r'[^\d]', '', str(cpf_str))
    if len(cpf) != 11:
        return False
    # All same digits is invalid
    if cpf == cpf[0] * 11:
        return False
    # First check digit
    total = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = 11 - (total % 11)
    d1 = 0 if d1 >= 10 else d1
    if int(cpf[9]) != d1:
        return False
    # Second check digit
    total = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = 11 - (total % 11)
    d2 = 0 if d2 >= 10 else d2
    return int(cpf[10]) == d2


def normalize_cpf(cpf_str):
    """Convert any CPF format to XXX.XXX.XXX-XX."""
    raw = re.sub(r'[^\d]', '', str(cpf_str))
    if len(raw) != 11:
        return cpf_str
    return f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"


def extract_cpf_from_text(text):
    """Find CPF patterns in text. Returns list of normalized CPFs (validated only)."""
    found = set()
    # Pattern 1: formatted CPFs (XXX.XXX.XXX-XX variations)
    for match in CPF_PATTERN.finditer(str(text)):
        raw = re.sub(r'[^\d]', '', match.group(1))
        if len(raw) == 11 and validate_cpf(raw):
            found.add(normalize_cpf(raw))
    # Pattern 2: raw 11-digit numbers
    for match in CPF_RAW_PATTERN.finditer(str(text)):
        raw = match.group(1)
        if validate_cpf(raw):
            found.add(normalize_cpf(raw))
    return list(found)


def process_leads(rows):
    """Process leads.csv rows. Filter cofounders.
    Returns list of lead dicts."""
    leads = []
    for row in rows:
        phone = str(row.get('phone', row.get('telefone', row.get('Telefone', '')))).strip()
        name = str(row.get('name', row.get('nome', row.get('Nome', '')))).strip()

        if not phone:
            continue

        # Filter cofounders
        phone_clean = re.sub(r'[^\d]', '', phone)
        if any(cp in phone_clean for cp in COFOUNDER_PHONES):
            continue
        if any(cn.lower() in name.lower() for cn in COFOUNDER_NAMES if cn):
            continue

        lead = {
            'phone': phone,
            'phone_clean': phone_clean,
            'name': name,
            'funnel_stage': str(row.get('funnel_stage', row.get('etapa', ''))).strip(),
            'cpf': str(row.get('cpf', row.get('CPF', ''))).strip(),
            'email': str(row.get('email', row.get('Email', ''))).strip(),
            'renda': str(row.get('renda', row.get('Renda', ''))).strip(),
            'profissao': str(row.get('profissao', row.get('profissão', row.get('Profissão', '')))).strip(),
            'estado_civil': str(row.get('estado_civil', row.get('Estado Civil', ''))).strip(),
            'nascimento': str(row.get('nascimento', row.get('data_nascimento', ''))).strip(),
            'endereco': str(row.get('endereco', row.get('endereço', ''))).strip(),
            'cep': str(row.get('cep', row.get('CEP', ''))).strip(),
            'tipo_imovel': str(row.get('tipo_imovel', row.get('tipo', ''))).strip(),
            'uso_imovel': str(row.get('uso_imovel', row.get('uso', ''))).strip(),
            'aluguel': str(row.get('aluguel', row.get('Aluguel', ''))).strip(),
            'condominio': str(row.get('condominio', row.get('Condomínio', ''))).strip(),
            'iptu': str(row.get('iptu', row.get('IPTU', ''))).strip(),
            'prazo': str(row.get('prazo', row.get('prazo_contrato', ''))).strip(),
            'coberturas': str(row.get('coberturas', row.get('Coberturas', ''))).strip(),
            'source': str(row.get('source', row.get('fonte', ''))).strip(),
        }
        leads.append(lead)

    return leads


def find_new_cpfs(historico_rows, known_cpfs, last_processed_row=0):
    """Search historico for new CPFs in incoming messages.
    known_cpfs: set of raw 11-digit CPF strings.
    Returns list of {phone, cpf, message_text, row_number}."""
    discoveries = []
    known_raw = set(re.sub(r'[^\d]', '', c) for c in known_cpfs)
    known_raw.discard('')

    for i, row in enumerate(historico_rows):
        if i < last_processed_row:
            continue

        # Only check incoming messages (from the lead, not the bot)
        direction = str(row.get('direction', row.get('direcao', row.get('tipo', '')))).strip().lower()
        if direction not in ('incoming', 'in', 'entrada', 'received', ''):
            # If direction field is not clear, check anyway
            pass

        phone = str(row.get('phone', row.get('telefone', row.get('Telefone', '')))).strip()
        message = str(row.get('message', row.get('mensagem', row.get('Mensagem', row.get('body', ''))))).strip()

        if not message:
            continue

        # Filter cofounder messages
        phone_clean = re.sub(r'[^\d]', '', phone)
        if any(cp in phone_clean for cp in COFOUNDER_PHONES):
            continue

        # Extract CPFs from message
        cpfs = extract_cpf_from_text(message)
        for cpf in cpfs:
            raw = re.sub(r'[^\d]', '', cpf)
            if raw not in known_raw:
                discoveries.append({
                    'phone': phone,
                    'phone_clean': phone_clean,
                    'cpf': cpf,
                    'cpf_raw': raw,
                    'message_text': message[:200],
                    'row_number': i
                })
                known_raw.add(raw)  # Don't discover same CPF twice

    return discoveries


def detect_data_changes(leads_rows, known_data):
    """Compare current leads data with known data.
    known_data: dict of phone_clean -> {field: value}
    Returns list of {phone, field, old_value, new_value}."""
    changes = []
    fields_to_check = [
        'endereco', 'cep', 'condominio', 'iptu', 'prazo',
        'coberturas', 'email', 'profissao', 'renda', 'estado_civil',
        'nascimento', 'tipo_imovel', 'aluguel'
    ]

    leads = process_leads(leads_rows)
    for lead in leads:
        phone = lead['phone_clean']
        if phone not in known_data:
            continue

        old = known_data[phone]
        for field in fields_to_check:
            new_val = lead.get(field, '').strip()
            old_val = str(old.get(field, '')).strip()
            # Check if there's new data where there wasn't before
            if new_val and new_val != old_val and new_val not in ('', 'nan', 'None', '—'):
                changes.append({
                    'phone': phone,
                    'name': lead.get('name', ''),
                    'field': field,
                    'old_value': old_val or '(empty)',
                    'new_value': new_val
                })

    return changes


def count_dados_completos(dashboard_dados_rows, cofounder_phones=None):
    """Count leads that shared ALL data (tem_cpf, tem_endereco, tem_aluguel, tem_renda = SIM).
    Uses the dashboard_dados Google Sheets tab."""
    if not dashboard_dados_rows:
        return 0
    if cofounder_phones is None:
        cofounder_phones = {'59899143298', '5599143298'}  # Martin
    count = 0
    for r in dashboard_dados_rows:
        phone = r.get('phone', '')
        name = r.get('name', '').lower()
        # Filter cofounders
        if any(c in phone for c in cofounder_phones):
            continue
        if any(x in name for x in ['martin', 'bernardo', 'elisa pereira']):
            continue
        if (r.get('tem_cpf', '') == 'SIM' and
            r.get('tem_endereco', '') == 'SIM' and
            r.get('tem_aluguel', '') == 'SIM' and
            r.get('tem_renda', '') == 'SIM'):
            count += 1
    return count


def compute_kpis(scores, pendente, brokers, total_leads, dados_completos=0):
    """Calculate KPI values for the dashboard."""
    n_scores = len(scores)
    n_pendente = len(pendente)
    n_invalid = len(brokers.get('invalid_cpf', []))
    n_rejected = len(brokers.get('rejected', []))
    n_approved = len(brokers.get('approved', []))

    # Count broker-only entries (rejected without score)
    broker_only_cpfs = set()
    for b in brokers.get('rejected', []):
        cpf_raw = re.sub(r'[^\d]', '', b.get('cpf', ''))
        # Check if this CPF is already in scores
        scored_cpfs = set(re.sub(r'[^\d]', '', s.get('cpf', '')) for s in scores)
        if cpf_raw not in scored_cpfs:
            broker_only_cpfs.add(cpf_raw)

    total_cpfs = n_scores + n_pendente + len(broker_only_cpfs) + n_invalid

    # Count enviados = total sent to broker (approved + rejected)
    # Also count any scored leads with "Enviado" status not already in broker lists
    broker_cpfs = set()
    for b in brokers.get('approved', []) + brokers.get('rejected', []):
        broker_cpfs.add(re.sub(r'[^\d]', '', b.get('cpf', '')))
    n_enviados = n_approved + n_rejected
    for s in scores:
        if 'Enviado' in s.get('status', ''):
            cpf_raw = re.sub(r'[^\d]', '', s.get('cpf', ''))
            if cpf_raw not in broker_cpfs:
                n_enviados += 1

    # Count ready
    n_ready = sum(1 for s in scores if 'Ready' in s.get('status', ''))

    return {
        'total_leads': total_leads,
        'cpfs': total_cpfs,
        'dados_completos': dados_completos,
        'verificado': n_scores,
        'sem_score': n_pendente,
        'cpf_errado': n_invalid,
        'enviados': n_enviados,
        'recusadas': n_rejected,
        'ready': n_ready
    }


def save_csv_cache(name, rows, cache_dir=None):
    """Save CSV rows to a JSON cache file."""
    if cache_dir is None:
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{name}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False)
    print(f"  Cached: {path} ({len(rows)} rows)")


def load_csv_cache(name, cache_dir=None):
    """Load CSV rows from cache."""
    if cache_dir is None:
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cache")
    path = os.path.join(cache_dir, f"{name}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


if __name__ == '__main__':
    print("=" * 50)
    print("Lumi CRM — Data Fetcher Test")
    print("=" * 50)

    # Test CPF validation
    print("\n[1] CPF Validation:")
    test_cpfs = [
        ("739.976.929-04", True),   # Roberto (valid)
        ("087.381.466-57", True),   # Adriano (valid)
        ("032.736.629-07", False),  # Fabiana (invalid)
        ("445.337.188-00", False),  # Bruna Caroline (invalid)
        ("111.111.111-11", False),  # All same (invalid)
    ]
    all_pass = True
    for cpf, expected in test_cpfs:
        result = validate_cpf(cpf)
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_pass = False
        print(f"  {status} {cpf}: valid={result} (expected={expected})")
    print(f"  {'All tests passed!' if all_pass else 'SOME TESTS FAILED!'}")

    # Test CPF normalization
    print("\n[2] CPF Normalization:")
    print(f"  08738146657 → {normalize_cpf('08738146657')}")
    print(f"  087.381.466-57 → {normalize_cpf('087.381.466-57')}")

    # Test CPF extraction
    print("\n[3] CPF Extraction from text:")
    test_text = "Meu cpf é 087.381.466-57 e o da minha mãe é 08973814665"
    found = extract_cpf_from_text(test_text)
    print(f"  Found: {found}")

    # Fetch CSVs
    print("\n[4] Fetching CSVs from Google Sheets...")
    try:
        csvs = fetch_all_csvs()
        for name, rows in csvs.items():
            print(f"  {name}: {len(rows)} rows")

        # Process leads
        print("\n[5] Processing leads...")
        leads = process_leads(csvs['leads'])
        print(f"  Total leads (excl. cofounders): {len(leads)}")

        # Check CPFs in leads
        cpf_count = sum(1 for l in leads if l['cpf'] and l['cpf'] not in ('', 'nan', 'None'))
        print(f"  Leads with CPF in CSV: {cpf_count} ({cpf_count*100//len(leads)}%)")

        # Search historico for CPFs
        print("\n[6] Searching historico for CPFs...")
        known_cpfs = set()  # empty set = find ALL CPFs
        discoveries = find_new_cpfs(csvs['historico'], known_cpfs)
        print(f"  Found {len(discoveries)} CPFs in historico messages")
        for d in discoveries[:5]:
            print(f"    {d['cpf']} (phone: {d['phone'][:15]}...)")
        if len(discoveries) > 5:
            print(f"    ... and {len(discoveries) - 5} more")

        # Cache for later use
        print("\n[7] Caching CSVs...")
        for name, rows in csvs.items():
            save_csv_cache(name, rows)

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()

    print("\nDone!")
