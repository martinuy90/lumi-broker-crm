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


def _is_filled(value):
    """Check if a field value is meaningfully filled (not empty/null)."""
    if value is None:
        return False
    s = str(value).strip().lower()
    return s not in ('', 'nan', 'none', '—', '-', '[]', '0')


def _compute_falta(lead_data, dashboard_flags=None):
    """Compute the 'falta' string from actual field data.

    Strategy:
    1. dashboard_dados flags give a BROAD picture (tem_cpf, tem_endereco, etc.)
    2. leads CSV structured columns are the GRANULAR authority
    3. Even when all 4 flags = SIM, we MUST check granular fields
       because the flags don't track CEP, IPTU, condominio, prazo, etc.
    4. If leads CSV has structured data, use it for specific missing-field detection
    5. If leads CSV is empty (data only in chat), note that verification is needed

    lead_data: dict from leads CSV raw row (or empty dict if no match)
    dashboard_flags: dict with tem_cpf/tem_endereco/tem_aluguel/tem_renda (or None)

    Returns (falta_string, is_complete) tuple.
    """
    # ── Check dashboard_dados flags first ──
    if dashboard_flags:
        has_cpf = dashboard_flags.get('tem_cpf', '') == 'SIM'
        has_endereco = dashboard_flags.get('tem_endereco', '') == 'SIM'
        has_aluguel = dashboard_flags.get('tem_aluguel', '') == 'SIM'
        has_renda = dashboard_flags.get('tem_renda', '') == 'SIM'

        all_flags_sim = has_cpf and has_endereco and has_aluguel and has_renda

        # ── GRANULAR CHECK: even when all flags = SIM, verify specific fields ──
        if lead_data:
            # Count how many structured fields the leads CSV actually has
            csv_filled_count = _count_filled_csv_fields(lead_data)

            if csv_filled_count >= 3:
                # Leads CSV has meaningful structured data → do granular check
                specific_missing = _check_fields_from_csv(lead_data)

                if not specific_missing:
                    # All granular fields confirmed present in CSV
                    return ('\u2713 Dados completos', True)

                if all_flags_sim:
                    # Dashboard says complete, but CSV reveals missing fields
                    # Don't mark as complete — return specific missing fields
                    return ('Falta: ' + ', '.join(specific_missing), False)
                else:
                    # Some flags NAO + CSV confirms specific gaps
                    return ('Falta: ' + ', '.join(specific_missing), False)

            else:
                # Leads CSV has little/no structured data (data is in chat only)
                if all_flags_sim:
                    # Flags say complete, but we can't verify granular fields
                    # Mark as needing verification rather than blindly trusting
                    return ('Falta: verificar detalhes', False)
                else:
                    # Some flags NAO and no CSV data — report what flags say is missing
                    # Note: CPF is NOT included here because scored leads already have CPF
                    # (from credit consultation), and this function is only called for scored leads
                    missing = []
                    if not has_renda:
                        missing.append('renda')
                    if not has_endereco:
                        missing.append('endereco')
                    if not has_aluguel:
                        missing.append('aluguel')
                    if missing:
                        return ('Falta: ' + ', '.join(missing), False)
                    return ('Falta: verificar detalhes', False)

        else:
            # No leads CSV match at all
            if all_flags_sim:
                return ('Falta: verificar detalhes', False)

            missing = []
            if not has_renda:
                missing.append('renda')
            if not has_endereco:
                missing.append('endereco')
            if not has_aluguel:
                missing.append('aluguel')
            if missing:
                return ('Falta: ' + ', '.join(missing), False)
            return ('Falta: verificar detalhes', False)

    # ── Fallback: no dashboard flags, use leads CSV fields directly ──
    if lead_data:
        csv_filled_count = _count_filled_csv_fields(lead_data)
        if csv_filled_count < 3:
            # Almost no structured data — can't determine
            return (None, False)

        specific_missing = _check_fields_from_csv(lead_data)
        if not specific_missing:
            return ('\u2713 Dados completos', True)

        if len(specific_missing) >= 10:
            return ('Falta: Dados pessoais + imóvel', False)
        elif all(m in ('endereco', 'CEP', 'tipo imovel', 'uso imovel', 'aluguel',
                       'condominio', 'IPTU', 'prazo contrato') for m in specific_missing):
            if len(specific_missing) >= 6:
                return ('Falta: Dados imóvel', False)
        return ('Falta: ' + ', '.join(specific_missing), False)

    # ── No match at all — can't determine, leave unchanged ──
    return (None, False)


def _count_filled_csv_fields(lead_data):
    """Count how many of the broker-required fields have data in the leads CSV.
    Used to determine if the CSV has meaningful structured data or is mostly empty.
    Returns count of filled fields (0-14)."""
    all_keys = [
        'email', 'birth_date', 'estado_civil', 'profissao', 'renda',
        'cpf', 'endereco_imovel', 'cep_imovel', 'tipo_imovel', 'uso_imovel',
        'aluguel', 'condominio', 'iptu', 'periodo_contrato'
    ]
    alt_keys = {
        'profissao': ['profissão', 'Profissão'],
        'birth_date': ['nascimento', 'data_nascimento'],
        'estado_civil': ['Estado Civil'],
        'endereco_imovel': ['endereco', 'endereço'],
        'cep_imovel': ['cep', 'CEP'],
        'periodo_contrato': ['prazo', 'prazo_contrato'],
        'cpf': ['CPF'],
    }
    count = 0
    for key in all_keys:
        val = lead_data.get(key, '')
        if _is_filled(val):
            count += 1
        else:
            # Try alternate keys
            for alt in alt_keys.get(key, []):
                if _is_filled(lead_data.get(alt, '')):
                    count += 1
                    break
    return count


def _check_fields_from_csv(lead_data):
    """Check which specific broker-required fields are missing from leads CSV data.
    Returns list of missing field labels.

    Broker-required fields:
      Personal: email, nascimento, estado civil, profissao, renda
      Property: endereco, CEP (CRITICAL), tipo imovel, uso imovel, aluguel,
                condominio, IPTU, prazo contrato
    Note: CPF and nome are tracked separately (via scores.json), not checked here.
    """
    personal_fields = {
        'email': 'email',
        'birth_date': 'nascimento',
        'estado_civil': 'estado civil',
        'profissao': 'profissao',
        'renda': 'renda',
    }
    property_fields = {
        'endereco_imovel': 'endereco',
        'cep_imovel': 'CEP',
        'tipo_imovel': 'tipo imovel',
        'uso_imovel': 'uso imovel',
        'aluguel': 'aluguel',
        'condominio': 'condominio',
        'iptu': 'IPTU',
        'periodo_contrato': 'prazo contrato',
    }
    alt_keys = {
        'profissao': ['profissão', 'Profissão'],
        'birth_date': ['nascimento', 'data_nascimento'],
        'estado_civil': ['Estado Civil'],
        'endereco_imovel': ['endereco', 'endereço'],
        'cep_imovel': ['cep', 'CEP'],
        'periodo_contrato': ['prazo', 'prazo_contrato'],
    }

    missing = []
    for fields in [personal_fields, property_fields]:
        for csv_key, label in fields.items():
            val = lead_data.get(csv_key, '')
            if not _is_filled(val):
                for alt in alt_keys.get(csv_key, []):
                    val = lead_data.get(alt, '')
                    if _is_filled(val):
                        break
            if not _is_filled(val):
                missing.append(label)

    # Special case: condominio/IPTU can be "incluso" (included in rent package)
    condo_val = str(lead_data.get('condominio', '')).lower()
    iptu_val = str(lead_data.get('iptu', '')).lower()
    if 'inclus' in condo_val or 'pacote' in condo_val:
        missing = [m for m in missing if m != 'condominio']
    if 'inclus' in iptu_val or 'pacote' in iptu_val:
        missing = [m for m in missing if m != 'IPTU']

    return missing


def _compute_status(score, falta_str, is_complete, broker_status=None, composicao=None, nao_enviar=False):
    """Compute status from score + falta. Returns (status_text, row_class)."""
    if broker_status in ('aprovado', 'enviado'):
        return ('Enviado \u2713', 'ry')
    if broker_status == 'recusada':
        return ('Recusada', 'ro')
    if composicao:
        return ('Composição', 'ry')
    if nao_enviar:
        return ('Não enviar', 'rr')
    if is_complete and score >= 400:
        return ('Ready \u2713', 'rg')
    if score >= 400:
        return ('Coletar dados', 'ry')
    if score >= 200:
        return ('Score baixo', 'ro' if score >= 277 else 'rr')
    if score > 0:
        return ('Sem chance', 'rr')
    return ('Consultar', 'ry')


def sync_scores_with_sheets(scores, leads_rows, dashboard_dados_rows=None, historico_rows=None, brokers=None):
    """Sync scores.json entries with fresh Google Sheet data.

    For each scored lead:
    1. Match to leads CSV by phone, CPF, or name
    2. Compute what fields are actually filled vs missing
    3. Update falta, status, renda, phone

    Modifies scores list in place. Returns count of updated entries.
    """
    if not leads_rows:
        return 0

    # Build set of CPFs already sent to broker (approved/rejected) — skip these
    broker_cpfs = set()
    if brokers:
        for b in brokers.get('approved', []) + brokers.get('rejected', []):
            broker_cpfs.add(re.sub(r'[^\d]', '', b.get('cpf', '')))

    # ── Build lookup maps ──

    # phone → lead data (from leads CSV)
    phone_to_lead = {}
    for row in leads_rows:
        phone = re.sub(r'[^\d]', '', str(row.get('phone', '')))
        if phone:
            phone_to_lead[phone] = row

    # CPF → phone (from leads CSV, for leads that have CPF)
    cpf_to_phone = {}
    for row in leads_rows:
        cpf = re.sub(r'[^\d]', '', str(row.get('cpf', '')))
        phone = re.sub(r'[^\d]', '', str(row.get('phone', '')))
        if len(cpf) == 11 and phone:
            cpf_to_phone[cpf] = phone

    # CPF → phone (from historico, for CPFs shared via WhatsApp messages)
    if historico_rows:
        for row in historico_rows:
            phone = re.sub(r'[^\d]', '', str(row.get('phone', '')))
            message = str(row.get('message', row.get('body', row.get('mensagem', ''))))
            if not message or not phone:
                continue
            cpfs_found = extract_cpf_from_text(message)
            for cpf in cpfs_found:
                cpf_raw = re.sub(r'[^\d]', '', cpf)
                if cpf_raw not in cpf_to_phone:
                    cpf_to_phone[cpf_raw] = phone

    # name (lowercased) → phone (from leads CSV, for name matching)
    name_to_phone = {}
    for row in leads_rows:
        name = str(row.get('name', '')).strip().lower()
        phone = re.sub(r'[^\d]', '', str(row.get('phone', '')))
        if name and phone:
            name_to_phone[name] = phone

    # phone → dashboard_dados flags
    phone_to_flags = {}
    if dashboard_dados_rows:
        for row in dashboard_dados_rows:
            phone = re.sub(r'[^\d]', '', str(row.get('phone', '')))
            if phone:
                phone_to_flags[phone] = row

    # ── Match and update each scored lead ──
    updated = 0
    for entry in scores:
        cpf_raw = re.sub(r'[^\d]', '', entry.get('cpf', ''))

        # Skip entries with special statuses that shouldn't be auto-updated
        if entry.get('broker_status') in ('aprovado', 'enviado', 'recusada'):
            continue
        # Skip if CPF is in broker lists (approved/rejected)
        if cpf_raw in broker_cpfs:
            continue
        # Skip composição leads (stored as field or in falta string)
        if entry.get('composicao'):
            continue
        existing_falta = entry.get('falta', '')
        if 'Composição' in existing_falta or 'Composição' in existing_falta:
            continue
        if entry.get('nao_enviar'):
            continue

        # ── Step 1: Find phone number ──
        phone = entry.get('phone', '')
        if not phone:
            # Try CPF → phone
            phone = cpf_to_phone.get(cpf_raw, '')
        if not phone:
            # Try name matching
            entry_name = entry.get('name', '').strip().lower()
            if entry_name:
                # Try exact match first
                phone = name_to_phone.get(entry_name, '')
                if not phone:
                    # Try substring match (handles "BRUNO DA COSTA BALBINOTTI" vs "Bruno")
                    for lead_name, lead_phone in name_to_phone.items():
                        if (entry_name in lead_name or lead_name in entry_name) and len(min(entry_name, lead_name, key=len)) > 3:
                            phone = lead_phone
                            break

        if not phone:
            # No match possible — leave as is
            continue

        # Store phone for future runs
        entry['phone'] = phone

        # ── Step 2: Get lead data and dashboard flags ──
        lead_data = phone_to_lead.get(phone, {})
        dashboard_flags = phone_to_flags.get(phone, None)

        # ── Step 3: Compute falta ──
        falta_str, is_complete = _compute_falta(lead_data, dashboard_flags)

        # If _compute_falta returned None, we have no data to update — skip
        if falta_str is None:
            continue

        # ── Step 4: Compute status ──
        score = entry.get('score', 0)
        status, row_class = _compute_status(
            score, falta_str, is_complete,
            broker_status=entry.get('broker_status'),
            composicao=entry.get('composicao'),
            nao_enviar=entry.get('nao_enviar', False)
        )

        # ── Step 5: Update renda from leads CSV ──
        renda_csv = str(lead_data.get('renda', '')).strip()
        if _is_filled(renda_csv):
            try:
                renda_num = float(re.sub(r'[^\d.]', '', renda_csv))
                renda_display = f'R${renda_num:,.0f}'.replace(',', '.')
            except (ValueError, TypeError):
                renda_display = f'R${renda_csv}'
        else:
            renda_display = entry.get('renda', '—')

        # ── Step 6: Update profissao from leads CSV ──
        prof_csv = str(lead_data.get('profissao', lead_data.get('profissão', ''))).strip()
        if _is_filled(prof_csv):
            entry['profissao'] = prof_csv

        # ── Step 7: Apply updates ──
        old_falta = entry.get('falta', '')
        old_status = entry.get('status', '')

        entry['falta'] = falta_str
        entry['status'] = status
        entry['row_class'] = row_class
        entry['renda'] = renda_display

        if old_falta != falta_str or old_status != status:
            updated += 1
            name = entry.get('name', '?')
            print(f"  Updated: {name} | {old_falta} → {falta_str} | {old_status} → {status}")

    return updated


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
