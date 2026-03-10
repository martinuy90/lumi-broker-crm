#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_html.py - Generates the complete Lumi Broker CRM dashboard HTML from JSON data.

Architecture:
  - Reads from: data/scores.json, data/pendente.json, data/brokers.json, data/config.json
  - Outputs: index.html (complete standalone HTML with inline CSS/JS)
  - Called by: update_crm.py

Usage:
  from generate_html import generate_html
  html = generate_html(scores, pendente, brokers, config, kpis, "7.1", "summary...")
"""

import json
import os
import re
import sys
from datetime import datetime


def _add_nome(entries):
    """Ensure all entries have 'nome' key (alias of 'name' for Portuguese templates)."""
    for e in entries:
        if 'name' in e and 'nome' not in e:
            e['nome'] = e['name']


def _normalize_brokers(raw, scores=None):
    """Normalize broker data to expected format.
    Handles both old format (aprovados/recusadas/invalid_cpfs) and
    new format (approved/rejected/invalid_cpf)."""
    if scores is None:
        scores = []
    result = dict(raw)  # shallow copy

    # Handle approved/aprovados
    if 'approved' in raw and 'aprovados' not in raw:
        result['aprovados'] = raw['approved']
    if 'aprovados' not in result:
        result['aprovados'] = []

    # Handle rejected/recusadas + derive broker_only
    rejected = raw.get('rejected', raw.get('recusadas', []))
    if 'recusadas' not in result:
        result['recusadas'] = rejected
    if 'broker_only' not in result:
        scored_cpfs = set(re.sub(r'[^\d]', '', s.get('cpf', '')) for s in scores)
        result['broker_only'] = [r for r in rejected if re.sub(r'[^\d]', '', r.get('cpf', '')) not in scored_cpfs]

    # Handle invalid_cpf/invalid_cpfs
    invalid = raw.get('invalid_cpf', raw.get('invalid_cpfs', []))
    if 'invalid_cpfs' not in result:
        result['invalid_cpfs'] = invalid
    if 'invalid_cpfs_enviados' not in result:
        result['invalid_cpfs_enviados'] = invalid

    # Auto-construct 'details' dicts for card rendering
    for e in result.get('aprovados', []):
        if 'details' not in e:
            d = {}
            if e.get('broker'):
                d['Broker'] = {'text': f'{e["broker"]} APROVADO', 'style': 'color:var(--green)'}
            if e.get('insurer'):
                d['Seguradora'] = e['insurer']
            if e.get('valor'):
                d['Valor'] = e['valor']
            if e.get('vigencia'):
                d['Vig\u00eancia'] = e['vigencia']
            if d:
                e['details'] = d
    for e in result.get('recusadas', []):
        if 'details' not in e:
            d = {}
            if e.get('profissao'):
                d['Profiss\u00e3o'] = e['profissao']
            if e.get('renda'):
                d['Renda'] = e['renda']
            if e.get('broker_notes'):
                d['Broker'] = e['broker_notes']
            if d:
                e['details'] = d
    for e in result.get('invalid_cpfs_enviados', []):
        if 'details' not in e:
            d = {}
            if e.get('renda'):
                d['Renda'] = e['renda']
            if e.get('phone'):
                d['Telefone'] = e['phone']
            if d:
                e['details'] = d
            if 'nota' not in e:
                e['nota'] = 'CPF inv\u00e1lido.'

    # Handle pending_broker
    if 'pending_broker' in raw:
        result['pending_broker'] = raw['pending_broker']
    if 'pending_broker' not in result:
        result['pending_broker'] = []

    # Normalize name → nome in all entry lists
    for key in ['aprovados', 'recusadas', 'invalid_cpfs', 'invalid_cpfs_enviados', 'broker_only', 'pending_broker']:
        _add_nome(result.get(key, []))

    # Set default broker_names
    if 'broker_names' not in result:
        result['broker_names'] = 'Arcoseg (Alice) \u00b7 Ittu (Itallo) \u00b7 Darqs (Graziele)'

    return result


def get_css():
    """Returns the complete CSS string from current v7.0 dashboard."""
    return (
        "*{margin:0;padding:0;box-sizing:border-box}\n"
        ":root{--bg:#0b0d13;--bg2:#131628;--bg3:#1a1d35;--card:#1e2140;--purple:#8b6cf6;--purpleL:#a98ff7;--purpleD:#6e54d4;--txt:#e8eaf6;--txt2:#8b92b0;--green:#10b981;--yellow:#f59e0b;--orange:#f97316;--red:#ef4444;--border:#2a2f4a}\n"
        "body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--txt);line-height:1.6;overflow-x:hidden}\n"
        ".wrap{max-width:1400px;margin:0 auto;padding:20px}\n"
        ".hdr{background:linear-gradient(135deg,var(--bg2),var(--bg3));border:1px solid var(--border);border-radius:12px;padding:24px;margin-bottom:20px}\n"
        ".hdr-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;flex-wrap:wrap;gap:8px}\n"
        ".hdr h1{font-size:26px;color:var(--purpleL);font-weight:700}\n"
        ".hdr h1 span{color:var(--txt2);font-weight:400;font-size:14px;margin-left:8px}\n"
        ".ts{font-size:11px;color:var(--txt2)}\n"
        ".kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:18px}\n"
        ".kpi{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px 10px;text-align:center}\n"
        ".kpi-v{font-size:28px;font-weight:800}.kpi-l{font-size:10px;text-transform:uppercase;letter-spacing:.8px;color:var(--txt2);margin-top:2px}\n"
        ".summ{background:linear-gradient(135deg,rgba(139,108,246,.12),rgba(139,108,246,.04));border:1px solid var(--purpleD);border-radius:8px;padding:14px 18px;font-size:13px;line-height:1.7;color:var(--txt)}\n"
        ".summ b{color:var(--purpleL)}\n"
        ".tabs{display:flex;gap:4px;margin-bottom:20px;border-bottom:1px solid var(--border);flex-wrap:wrap;padding-bottom:0}\n"
        ".tab{padding:10px 18px;background:transparent;border:none;color:var(--txt2);cursor:pointer;font-size:13px;font-weight:500;border-bottom:2px solid transparent;transition:.2s;letter-spacing:.3px}\n"
        ".tab:hover{color:var(--purpleL)}.tab.on{color:var(--purpleL);border-bottom-color:var(--purple)}\n"
        ".tab .cnt{background:var(--purple);color:#fff;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;margin-left:5px}\n"
        ".sec{display:none}.sec.on{display:block}\n"
        ".rtitle{font-size:17px;font-weight:600;color:var(--purpleL);margin-bottom:14px;display:flex;align-items:center;gap:8px}\n"
        ".tbl{width:100%;border-collapse:collapse;background:var(--card);border-radius:8px;overflow:hidden;border:1px solid var(--border);font-size:13px}\n"
        ".tbl thead{background:linear-gradient(90deg,var(--purpleD),var(--purple))}\n"
        ".tbl th{padding:11px 12px;text-align:left;font-weight:600;color:#fff;font-size:11px;text-transform:uppercase;letter-spacing:.5px}\n"
        ".tbl td{padding:10px 12px;border-bottom:1px solid var(--border)}\n"
        ".tbl tbody tr:last-child td{border-bottom:none}\n"
        ".tbl tbody tr:hover{background:rgba(139,108,246,.08)}\n"
        ".mono{font-family:'Courier New',monospace;font-size:11px;color:var(--txt2)}\n"
        ".sc{font-weight:700;font-size:14px;text-align:center}\n"
        ".badge{display:inline-block;padding:3px 9px;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;min-width:65px;text-align:center}\n"
        ".b-bom{background:rgba(16,185,129,.18);color:var(--green);border:1px solid rgba(16,185,129,.4)}\n"
        ".b-reg{background:rgba(245,158,11,.18);color:var(--yellow);border:1px solid rgba(245,158,11,.4)}\n"
        ".b-bai{background:rgba(249,115,22,.18);color:var(--orange);border:1px solid rgba(249,115,22,.4)}\n"
        ".b-rui{background:rgba(239,68,68,.18);color:var(--red);border:1px solid rgba(239,68,68,.4)}\n"
        ".b-inv{background:rgba(239,68,68,.25);color:#ff6b6b;border:1px solid rgba(239,68,68,.5)}\n"
        ".b-rec{background:rgba(239,68,68,.12);color:#f87171;border:1px solid rgba(239,68,68,.3)}\n"
        ".st{display:inline-block;padding:3px 9px;border-radius:4px;font-size:10px;font-weight:600;letter-spacing:.2px}\n"
        ".st-col{background:rgba(96,165,250,.15);color:#60a5fa;border:1px solid rgba(96,165,250,.3)}\n"
        ".st-imo{background:rgba(245,158,11,.15);color:#fbbf24;border:1px solid rgba(245,158,11,.3)}\n"
        ".st-prn{background:rgba(16,185,129,.15);color:#34d399;border:1px solid rgba(16,185,129,.3)}\n"
        ".st-env{background:rgba(139,108,246,.15);color:#a78bfa;border:1px solid rgba(139,108,246,.3)}\n"
        ".st-rec{background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3)}\n"
        ".st-inv{background:rgba(239,68,68,.25);color:#ff6b6b;border:1px solid rgba(239,68,68,.5)}\n"
        ".st-nao{background:rgba(107,114,128,.15);color:#9ca3af;border:1px solid rgba(107,114,128,.3)}\n"
        ".st-rdy{background:rgba(16,185,129,.25);color:#10b981;border:1px solid rgba(16,185,129,.5);font-weight:700}\n"
        ".rg{background:rgba(16,185,129,.06)}.ry{background:rgba(245,158,11,.06)}.ro{background:rgba(249,115,22,.06)}.rr{background:rgba(239,68,68,.06)}.rx{background:rgba(107,114,128,.06)}\n"
        ".cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px;margin-bottom:24px}\n"
        ".crd{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:18px;cursor:pointer;transition:.2s;position:relative}\n"
        ".crd:hover{border-color:var(--purple);box-shadow:0 4px 12px rgba(139,108,246,.15);transform:translateY(-1px)}\n"
        ".crd-h{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}\n"
        ".crd-n{font-size:15px;font-weight:600}.crd-sub{font-size:11px;color:var(--txt2);font-family:monospace;margin-top:2px}\n"
        ".crd-sc{text-align:center;min-width:50px}.crd-sc b{font-size:22px;font-weight:800;color:var(--purpleL)}.crd-sc .stars{color:var(--yellow);font-size:11px;letter-spacing:2px}\n"
        ".crd-body{display:none;margin-top:12px;padding-top:12px;border-top:1px solid var(--border);font-size:12px;line-height:1.8}\n"
        ".crd.open .crd-body{display:block}\n"
        ".crd-row{display:flex;gap:6px}.crd-row .l{color:var(--txt2);min-width:100px}.crd-row .v{color:var(--txt);font-weight:500}\n"
        ".crd-note{margin-top:10px;padding:10px;background:rgba(139,108,246,.08);border-radius:6px;border-left:3px solid var(--purple);font-size:11px;line-height:1.6}\n"
        ".crd-note b{color:var(--purpleL)}\n"
        ".crd-gl{border-left:4px solid var(--green)}.crd-rl{border-left:4px solid var(--red)}.crd-xl{border-left:4px solid #4b5563}\n"
        ".stitle{font-size:15px;font-weight:600;color:var(--purpleL);margin-bottom:16px;padding-left:10px;border-left:3px solid var(--purple)}\n"
        ".coll-h{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--card);border:1px solid var(--border);border-radius:8px;cursor:pointer;margin-bottom:12px;transition:.2s}\n"
        ".coll-h:hover{border-color:var(--purple)}\n"
        ".coll-t{font-weight:600;font-size:13px}.coll-c{background:var(--purple);color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700}\n"
        ".coll-b{display:none;margin-bottom:20px}.coll-b.open{display:block}\n"
        ".chv{color:var(--txt2);transition:.3s;font-size:11px}.coll-b.open+.placeholder .chv,.open~.chv{transform:rotate(180deg)}\n"
        "footer{text-align:center;padding:24px;border-top:1px solid var(--border);color:var(--txt2);font-size:11px;margin-top:30px}\n"
        "@media(max-width:768px){.kpis{grid-template-columns:repeat(2,1fr)}.cards{grid-template-columns:1fr}.tbl{font-size:11px}.tbl th,.tbl td{padding:8px 6px}.tab{padding:8px 12px;font-size:12px}}"
    )


def score_rating(score):
    """Returns (rating_text, badge_class, row_class, score_color).
    Sub-tiers within BAIXO (200-399):
      - 277-399: orange row/text (borderline, some brokers may accept)
      - 200-276: red row/text (very unlikely to be accepted)
    """
    if score >= 600:
        return ("BOM", "b-bom", "rg", "var(--green)")
    elif score >= 400:
        return ("REGULAR", "b-reg", "ry", "var(--yellow)")
    elif score >= 277:
        return ("BAIXO", "b-bai", "ro", "var(--orange)")
    elif score >= 200:
        return ("BAIXO", "b-bai", "rr", "var(--red)")
    else:
        return ("RUIM", "b-rui", "rr", "var(--red)")


def score_stars(score):
    """Returns star string based on score tier."""
    if score >= 600:
        return "\u2605\u2605\u2605"
    elif score >= 450:
        return "\u2605\u2605"
    elif score >= 400:
        return "\u2605"
    return ""


def determine_status(entry):
    """Determine display status and CSS class for a scored lead.
    Priority: stored status (Aprovado/Enviado/Recusada) > broker_status field >
              composicao > nao_enviar > Ready > score-based."""
    score = entry.get('score', 0)
    falta = entry.get('falta', '')
    broker_status = entry.get('broker_status', '')
    stored_status = entry.get('status', '')
    # Preserve already-set broker statuses from scores.json
    if stored_status.startswith('Aprovado'):
        return ('Aprovado \u2713', 'st-env')
    if stored_status.startswith('Enviado'):
        return ('Enviado \u2713', 'st-env')
    if stored_status == 'Recusada':
        return ('Recusada', 'st-rec')
    # Check broker_status field (set by sync)
    if broker_status in ('aprovado', 'enviado'):
        return ('Enviado \u2713', 'st-env')
    if broker_status == 'recusada':
        return ('Recusada', 'st-rec')
    if entry.get('composicao'):
        return ('Composi\u00e7\u00e3o', 'st-nao')
    if entry.get('nao_enviar'):
        return ('N\u00e3o enviar', 'st-nao')
    if '\u2713 Dados completos' in falta and score >= 400:
        return ('Ready \u2713', 'st-rdy')
    if score >= 400:
        return ('Coletar dados', 'st-imo')
    if score >= 200:
        return ('Score baixo', 'st-nao')
    if score > 0:
        return ('Sem chance', 'st-nao')
    return ('Consultar', 'st-col')


def falta_style(falta_text):
    """Returns inline style for the Falta column."""
    if not falta_text:
        return 'color:var(--txt2);font-size:11px'
    if '\u2713 Dados completos' in falta_text or '\u2713 Dados quase completos' in falta_text:
        return 'color:var(--green);font-size:11px'
    if 'Sem dados no sistema' in falta_text or 'Nome sujo' in falta_text or 'CPF inv' in falta_text:
        return 'color:var(--red);font-size:11px'
    return 'color:var(--orange);font-size:11px'


def _e(text):
    """HTML-escape a string."""
    if text is None:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def generate_header(kpis, version, summary_text):
    """Generate the header section with KPI boxes and summary."""
    now = datetime.now()
    date_str = now.strftime('%d/%m/%Y')
    kpi_defs = [
        ('total_leads', 'var(--purpleL)', 'Total Leads'),
        ('cpfs', '#60a5fa', 'CPFs Compartilhados'),
        ('dados_completos', '#34d399', 'Dados Completos'),
        ('verificado', 'var(--yellow)', 'Cr\u00e9dito Verificado'),
        ('sem_score', 'var(--yellow)', 'CPF Sem Score'),
        ('cpf_errado', 'var(--orange)', 'CPF Errado'),
        ('cotacao_enviada', 'var(--green)', 'Cota\u00e7\u00e3o Seguro Fian\u00e7a'),
        ('capitalizacao', 'var(--yellow)', 'Capitaliza\u00e7\u00e3o Enviada'),
    ]
    lines = []
    lines.append('<div class="hdr">')
    lines.append('  <div class="hdr-top">')
    lines.append('    <h1>Lumi Broker CRM <span>Gest\u00e3o de Leads Seguro Fian\u00e7a</span></h1>')
    lines.append(f'    <div class="ts">Atualizado: {date_str} \u2014 v{version}</div>')
    lines.append('  </div>')
    lines.append('  <div class="kpis">')
    for key, color, label in kpi_defs:
        v = kpis.get(key, 0)
        lines.append(f'    <div class="kpi"><div class="kpi-v" style="color:{color}">{v}</div><div class="kpi-l">{label}</div></div>')
    lines.append('  </div>')
    lines.append(f'  <div class="summ">')
    lines.append(f'    {summary_text}')
    lines.append('  </div>')
    lines.append('</div>')
    return '\n'.join(lines)


def generate_tabs(counts):
    """Generate tab buttons with counts."""
    tab_defs = [
        ('todos', 'Ranking Completo'),
        ('acao', 'A\u00e7\u00e3o Necess\u00e1ria'),
        ('enviados', 'Enviados/Recusados'),
        ('baixo', 'Sem Score'),
    ]
    lines = ['<div class="tabs">']
    for i, (key, label) in enumerate(tab_defs):
        active = ' on' if i == 0 else ''
        cnt = counts.get(key, 0)
        lines.append(f'  <button class="tab{active}" onclick="sw(\'{key}\',this)">{label}<span class="cnt">{cnt}</span></button>')
    lines.append('</div>')
    return '\n'.join(lines)


def generate_ranking_row(pos, entry, row_class):
    """Generate a single table row for a scored lead."""
    score = entry.get('score', 0)
    rating_text, badge_class, _, score_color = score_rating(score)
    status_text, status_class = determine_status(entry)
    pos_display = str(pos) if pos else '\u2014'
    bold_pos = entry.get('bold_pos', pos is not None and pos <= 7)
    pos_style = 'font-weight:700;color:var(--purpleL)' if bold_pos else ''
    name_style = ' style="font-weight:600"' if bold_pos else ''
    falta_text = entry.get('falta', '')
    falta_display = falta_text if falta_text else '\u2014'
    if entry.get('composicao'):
        falta_display = f'Composi\u00e7\u00e3o ({entry["composicao"]})'
        falta_st = 'color:var(--txt2);font-size:11px'
    else:
        falta_st = falta_style(falta_text)
    tr_extra = ' style="border-left:3px solid var(--purple)"' if entry.get('highlight') else ''
    renda = entry.get('renda', '\u2014') or '\u2014'
    L = []
    L.append(f'<tr class="{row_class}"{tr_extra}>')
    L.append(f'  <td style="{pos_style}">{pos_display}</td>' if pos_style else f'  <td>{pos_display}</td>')
    L.append(f'  <td{name_style}>{_e(entry.get("nome", ""))}</td>')
    L.append(f'  <td class="mono">{_e(entry.get("cpf", ""))}</td>')
    L.append(f'  <td class="sc" style="color:{score_color}">{score}</td>')
    L.append(f'  <td><span class="badge {badge_class}">{rating_text}</span></td>')
    L.append(f'  <td>{_e(renda)}</td>')
    L.append(f'  <td style="{falta_st}">{_e(falta_display)}</td>')
    L.append(f'  <td><span class="st {status_class}">{_e(status_text)}</span></td>')
    L.append('</tr>')
    return '\n'.join(L)


def generate_pendente_ranking_row(entry):
    """Generate a ranking table row for a PENDENTE (sem score) lead."""
    renda = entry.get('renda', '\u2014') or '\u2014'
    falta = entry.get('falta', 'Falta: Score')
    status_text = 'Consultar \u2605' if entry.get('top_priority') else 'Consultar'
    L = []
    L.append('<tr class="rx">')
    L.append('  <td>\u2014</td>')
    L.append(f'  <td>{_e(entry.get("nome", ""))}</td>')
    L.append(f'  <td class="mono">{_e(entry.get("cpf", ""))}</td>')
    L.append('  <td class="sc" style="color:var(--txt2)">?</td>')
    L.append('  <td><span class="badge" style="background:rgba(107,114,128,.15);color:var(--txt2)">PENDENTE</span></td>')
    L.append(f'  <td>{_e(renda)}</td>')
    L.append(f'  <td style="{falta_style(falta)}">{_e(falta)}</td>')
    L.append(f'  <td><span class="st st-col">{_e(status_text)}</span></td>')
    L.append('</tr>')
    return '\n'.join(L)


def generate_broker_ranking_row(entry):
    """Generate a ranking table row for broker-verified leads (no numeric score)."""
    renda = entry.get('renda', '\u2014') or '\u2014'
    falta = entry.get('falta', entry.get('broker_notes', ''))
    L = []
    L.append('<tr class="rx">')
    L.append('  <td>\u2014</td>')
    L.append(f'  <td>{_e(entry.get("name", entry.get("nome", "")))}</td>')
    L.append(f'  <td class="mono">{_e(entry.get("cpf", ""))}</td>')
    L.append('  <td class="sc" style="color:var(--txt2)">\u2014</td>')
    L.append('  <td><span class="badge b-rec">RECUSADA</span></td>')
    L.append(f'  <td>{_e(renda)}</td>')
    L.append(f'  <td style="{falta_style(falta)}">{_e(falta)}</td>')
    L.append('  <td><span class="st st-rec">Recusada</span></td>')
    L.append('</tr>')
    return '\n'.join(L)


def generate_invalid_cpf_ranking_row(entry):
    """Generate a ranking table row for invalid CPF leads."""
    renda = entry.get('renda', '\u2014') or '\u2014'
    L = []
    L.append('<tr style="background:rgba(239,68,68,.1)">')
    L.append('  <td>\u2014</td>')
    L.append(f'  <td>{_e(entry.get("name", entry.get("nome", "")))}</td>')
    L.append(f'  <td class="mono" style="color:#f87171;text-decoration:line-through">{_e(entry.get("cpf", ""))}</td>')
    L.append('  <td class="sc" style="color:var(--txt2)">\u2014</td>')
    L.append('  <td><span class="badge b-inv">INV\u00c1LIDO</span></td>')
    L.append(f'  <td>{_e(renda)}</td>')
    L.append('  <td style="color:var(--red);font-size:11px">CPF inv\u00e1lido</td>')
    L.append('  <td><span class="st st-inv">Pedir CPF</span></td>')
    L.append('</tr>')
    return '\n'.join(L)


def generate_ranking_table(scores, pendente, brokers):
    """Generate the complete ranking table (Tab 1)."""
    L = []
    L.append('<!-- ============ TAB 1: RANKING COMPLETO ============ -->')
    L.append('<div id="s-todos" class="sec on">')
    L.append('<div class="rtitle">Ranking Completo de Cr\u00e9dito Verificado</div>')
    L.append('<table class="tbl">')
    L.append('<thead><tr>')
    L.append('  <th style="width:3%">#</th>')
    L.append('  <th style="width:20%">Nome</th>')
    L.append('  <th style="width:12%">CPF</th>')
    L.append('  <th style="width:5%">Score</th>')
    L.append('  <th style="width:7%">Rating</th>')
    L.append('  <th style="width:10%">Renda</th>')
    L.append('  <th style="width:15%">Falta</th>')
    L.append('  <th style="width:13%">Status</th>')
    L.append('</tr></thead>')
    L.append('<tbody>')
    for i, entry in enumerate(scores, 1):
        s = entry.get('score', 0)
        _, _, rc, _ = score_rating(s)
        c = entry.get('comment', '')
        if c:
            L.append(f'<!-- {c} -->')
        L.append(generate_ranking_row(i, entry, rc))
    if pendente:
        L.append('<!-- \u2500\u2500 CPFs Sem Score (aguardando consulta) \u2500\u2500 -->')
        for e in pendente:
            c = e.get('comment', '')
            if c:
                L.append(f'<!-- {c} -->')
            L.append(generate_pendente_ranking_row(e))
    bo = brokers.get('broker_only', [])
    if bo:
        L.append('<!-- \u2500\u2500 Verificados pelo broker (sem score num\u00e9rico) \u2500\u2500 -->')
        for e in bo:
            L.append(generate_broker_ranking_row(e))
    ic = brokers.get('invalid_cpfs', [])
    if ic:
        L.append('<!-- \u2500\u2500 CPFs Inv\u00e1lidos \u2500\u2500 -->')
        for e in ic:
            L.append(generate_invalid_cpf_ranking_row(e))
    L.append('</tbody>')
    L.append('</table>')
    L.append('<p style="font-size:10px;color:var(--txt2);margin-top:8px">* Renda presumida pela consulta de cr\u00e9dito (n\u00e3o declarada pelo lead). "Sem dados no sistema" = lead n\u00e3o completou coleta de dados no bot.</p>')
    L.append('</div>')
    return '\n'.join(L)


def _card_row(label, value, value_style=''):
    """Generate a single card detail row."""
    st = f' style="{value_style}"' if value_style else ''
    return f'    <div class="crd-row"><span class="l">{_e(label)}:</span><span class="v"{st}>{_e(value)}</span></div>'


def _card_note(text, border_color='var(--purple)'):
    """Generate a card note section. text can contain HTML."""
    return f'    <div class="crd-note" style="border-left-color:{border_color}">\n      {text}\n    </div>'


def _falta_box(items_text):
    """Generate the red falta para enviar box."""
    return (
        '    <div style="margin-top:10px;padding:8px 10px;background:rgba(239,68,68,.08);'
        'border-radius:6px;border:1px solid rgba(239,68,68,.2);font-size:11px;color:#f87171">\n'
        f'      <b>Falta para enviar ao broker:</b> {_e(items_text)}\n'
        '    </div>'
    )


def _falta_box_html(html_content):
    """Generate the red falta box with raw HTML."""
    return (
        '    <div style="margin-top:10px;padding:8px 10px;background:rgba(239,68,68,.08);'
        'border-radius:6px;border:1px solid rgba(239,68,68,.2);font-size:11px;color:#f87171">\n'
        f'      {html_content}\n'
        '    </div>'
    )


def _render_details(details):
    """Render detail rows from a details dict."""
    rows = []
    for label, value in details.items():
        if isinstance(value, dict):
            rows.append(_card_row(label, value.get('text', ''), value.get('style', '')))
        else:
            rows.append(_card_row(label, str(value)))
    return rows


def generate_acao_card_cpf_errado(entry):
    """Generate a card for the CPF Errado section."""
    nome = entry.get('nome', '')
    cpf = entry.get('cpf', '')
    status_bot = entry.get('status_bot', '')
    nota = entry.get('nota', '')
    L = []
    L.append(f'<div class="crd" style="border-left:4px solid var(--orange)" onclick="this.classList.toggle(\'open\')">')
    L.append('  <div class="crd-h">')
    L.append('    <div>')
    L.append(f'      <div class="crd-n">{_e(nome)}</div>')
    L.append(f'      <div class="crd-sub" style="color:#f87171;text-decoration:line-through">CPF {_e(cpf)} (inv\u00e1lido)</div>')
    L.append('    </div>')
    L.append('    <span class="badge" style="background:rgba(249,115,22,.18);color:var(--orange);border:1px solid rgba(249,115,22,.4)">CPF ERRADO</span>')
    L.append('  </div>')
    if status_bot:
        bc = 'st-imo' if 'cotacao' in status_bot else 'st-col'
        L.append('  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">')
        L.append(f'    <span class="st {bc}">{_e(status_bot)}</span>')
        L.append('  </div>')
    L.append('  <div class="crd-body">')
    field_labels = {'telefone':'Telefone','whatsapp':'WhatsApp','profissao':'Profiss\u00e3o','renda':'Renda','email':'Email','aluguel':'Aluguel','cep':'CEP'}
    for field in ['telefone', 'whatsapp', 'profissao', 'renda', 'email', 'aluguel', 'cep']:
        v = entry.get(field, '')
        if v:
            L.append(_card_row(field_labels.get(field, field), v))
    if nota:
        L.append(_card_note(nota, 'var(--orange)'))
    L.append('  </div>')
    L.append('</div>')
    return '\n'.join(L)


def generate_acao_card_priority(entry):
    """Generate a card for priority leads in Acao Necessaria tab."""
    nome = entry.get('nome', '')
    cpf = entry.get('cpf', '')
    score = entry.get('score', 0)
    rating_text, badge_class, _, _ = score_rating(score)
    stars = score_stars(score)
    sc_color = 'var(--green)' if score >= 600 else ('var(--yellow)' if score >= 400 else 'var(--orange)')
    falta_short = entry.get('falta_short', entry.get('falta', ''))
    details = entry.get('details', {})
    falta_items = entry.get('falta_items', '')
    nota = entry.get('nota', '')
    L = []
    L.append(f'<div class="crd crd-gl" onclick="this.classList.toggle(\'open\')">')
    L.append('  <div class="crd-h">')
    L.append('    <div>')
    L.append(f'      <div class="crd-n">{_e(nome)}</div>')
    L.append(f'      <div class="crd-sub">CPF {_e(cpf)}</div>')
    L.append('    </div>')
    L.append(f'    <div class="crd-sc"><b style="color:{sc_color}">{score}</b>')
    if stars:
        L.append(f'<div class="stars">{stars}</div>')
    L.append('</div>')
    L.append('  </div>')
    L.append('  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">')
    L.append(f'    <span class="badge {badge_class}">{rating_text}</span>')
    if falta_short:
        L.append(f'    <span class="st st-imo">{_e(falta_short)}</span>')
    L.append('  </div>')
    L.append('  <div class="crd-body">')
    L.extend(_render_details(details))
    if falta_items:
        if '<b>' in falta_items:
            L.append(_falta_box_html(falta_items))
        else:
            L.append(_falta_box(falta_items))
    if nota:
        nc = entry.get('nota_color', 'var(--purple)')
        L.append(_card_note(nota, nc))
    L.append('  </div>')
    L.append('</div>')
    return '\n'.join(L)


def generate_acao_tab(scores, brokers):
    """Generate Tab 2: Acao Necessaria."""
    invalid_cpfs = brokers.get('invalid_cpfs', [])
    best = None
    priority = []
    for e in scores:
        s = e.get('score', 0)
        st, _ = determine_status(e)
        if s >= 400 and st == 'Coletar dados':
            if best is None:
                best = e
            else:
                priority.append(e)
    L = []
    L.append('<!-- ============ TAB 2: A\u00c7\u00c3O NECESS\u00c1RIA ============ -->')
    L.append('<div id="s-acao" class="sec">')
    if invalid_cpfs:
        L.append('<div class="stitle" style="color:var(--orange);border-left-color:var(--orange)">CPFs Incorretos \u2014 Precisam Pedir CPF Correto</div>')
        L.append('<div class="cards">')
        for e in invalid_cpfs:
            L.append(generate_acao_card_cpf_errado(e))
        L.append('</div>')
    if best:
        L.append('<div class="stitle" style="margin-top:24px;color:var(--green);border-left-color:var(--green)">Melhor Candidato \u2605 \u2014 Falta Dados do Im\u00f3vel</div>')
        L.append('<div class="cards">')
        L.append(generate_acao_card_priority(best))
        L.append('</div>')
    if priority:
        L.append('<div class="stitle" style="margin-top:24px">Coletar Dados \u2014 Score REGULAR (Prioridade)</div>')
        L.append('<div class="cards">')
        for e in priority:
            L.append(generate_acao_card_priority(e))
        L.append('</div>')
    L.append('</div>')
    return '\n'.join(L)


def generate_enviados_card_aprovado(entry):
    """Generate a card for an approved lead."""
    nome = entry.get('nome', '')
    cpf = entry.get('cpf', '')
    score = entry.get('score', 0)
    details = entry.get('details', {})
    nota = entry.get('nota', '')
    sub_parts = [f'CPF {cpf}']
    if score:
        sub_parts.append(f'Score {score}')
    sub_text = ' \u00b7 '.join(sub_parts)
    L = []
    L.append(f'<div class="crd crd-gl" onclick="this.classList.toggle(\'open\')">')
    L.append('  <div class="crd-h">')
    L.append(f'    <div><div class="crd-n">{_e(nome)}</div><div class="crd-sub">{_e(sub_text)}</div></div>')
    L.append('    <span class="badge" style="background:rgba(16,185,129,.25);color:var(--green);border:1px solid rgba(16,185,129,.5);font-weight:700">APROVADO \u2713</span>')
    L.append('  </div>')
    L.append('  <div class="crd-body">')
    L.extend(_render_details(details))
    if nota:
        L.append(_card_note(nota, 'var(--green)'))
    L.append('  </div>')
    L.append('</div>')
    return '\n'.join(L)


def generate_enviados_card_invalid(entry):
    """Generate a card for an invalid CPF lead in the Enviados tab."""
    nome = entry.get('nome', '')
    cpf = entry.get('cpf', '')
    details = entry.get('details', {})
    nota = entry.get('nota', '')
    L = []
    L.append(f'<div class="crd crd-rl" onclick="this.classList.toggle(\'open\')">')
    L.append('  <div class="crd-h">')
    L.append(f'    <div><div class="crd-n">{_e(nome)}</div><div class="crd-sub" style="color:#f87171;text-decoration:line-through">CPF {_e(cpf)}</div></div>')
    L.append('    <span class="badge b-inv">CPF INV\u00c1LIDO</span>')
    L.append('  </div>')
    L.append('  <div class="crd-body">')
    L.extend(_render_details(details))
    if nota:
        L.append(_card_note(nota, 'var(--red)'))
    L.append('  </div>')
    L.append('</div>')
    return '\n'.join(L)


def generate_enviados_card_recusada(entry):
    """Generate a card for a rejected lead."""
    nome = entry.get('nome', '')
    cpf = entry.get('cpf', '')
    score = entry.get('score', 0)
    details = entry.get('details', {})
    sub_parts = [f'CPF {cpf}']
    if score:
        sub_parts.append(f'Score {score}')
    sub_text = ' \u00b7 '.join(sub_parts)
    L = []
    L.append(f'<div class="crd crd-rl" onclick="event.stopPropagation();this.classList.toggle(\'open\')">')
    L.append(f'  <div class="crd-h"><div><div class="crd-n">{_e(nome)}</div><div class="crd-sub">{_e(sub_text)}</div></div><span class="badge b-rec">RECUSADA</span></div>')
    L.append('  <div class="crd-body">')
    L.extend(_render_details(details))
    L.append('  </div>')
    L.append('</div>')
    return '\n'.join(L)


def generate_pending_broker_card(entry):
    """Generate a card for a lead sent to broker, waiting for response."""
    nome = entry.get('nome', '')
    cpf = entry.get('cpf', '')
    score = entry.get('score', 0)
    broker = entry.get('broker', '')
    date_sent = entry.get('date_sent', '')
    details = entry.get('details', {})
    sub_parts = [f'CPF {cpf}']
    if score:
        sub_parts.append(f'Score {score}')
    if date_sent:
        sub_parts.append(f'Enviado {date_sent}')
    sub_text = ' \u00b7 '.join(sub_parts)
    L = []
    L.append(f'<div class="crd" style="border-left:4px solid #60a5fa" onclick="this.classList.toggle(\'open\')">')
    L.append('  <div class="crd-h">')
    L.append(f'    <div><div class="crd-n">{_e(nome)}</div><div class="crd-sub">{_e(sub_text)}</div></div>')
    L.append(f'    <span class="badge" style="background:rgba(96,165,250,.18);color:#60a5fa;border:1px solid rgba(96,165,250,.4);font-weight:700">AGUARDANDO</span>')
    L.append('  </div>')
    L.append('  <div class="crd-body">')
    L.extend(_render_details(details))
    L.append('  </div>')
    L.append('</div>')
    return '\n'.join(L)


def generate_capitalizacao_card(entry):
    """Generate a card for a capitalização candidate (rejected lead with complete data)."""
    nome = entry.get('nome', '')
    cpf = entry.get('cpf', '')
    score = entry.get('score', 0)
    details = entry.get('details', {})
    sub_parts = [f'CPF {cpf}']
    if score:
        sub_parts.append(f'Score {score}')
    sub_text = ' \u00b7 '.join(sub_parts)
    L = []
    L.append(f'<div class="crd" style="border-left:4px solid var(--yellow)" onclick="this.classList.toggle(\'open\')">')
    L.append('  <div class="crd-h">')
    L.append(f'    <div><div class="crd-n">{_e(nome)}</div><div class="crd-sub">{_e(sub_text)}</div></div>')
    L.append('    <span class="badge" style="background:rgba(245,158,11,.18);color:var(--yellow);border:1px solid rgba(245,158,11,.4);font-weight:700">CAPITALIZA\u00c7\u00c3O</span>')
    L.append('  </div>')
    L.append('  <div class="crd-body">')
    L.extend(_render_details(details))
    nota = entry.get('nota', 'Recusado no seguro fian\u00e7a. Dados completos \u2014 candidato para seguro de capitaliza\u00e7\u00e3o.')
    L.append(_card_note(nota, 'var(--yellow)'))
    L.append('  </div>')
    L.append('</div>')
    return '\n'.join(L)


def generate_enviados_tab(brokers):
    """Generate Tab 3: Enviados/Recusados."""
    aprovados = brokers.get('aprovados', [])
    pending_broker = brokers.get('pending_broker', [])
    invalid_enviados = brokers.get('invalid_cpfs_enviados', [])
    recusadas = brokers.get('recusadas', [])
    # Filter rejected leads with complete data for capitalização section
    capitalizacao = [r for r in recusadas if r.get('dados_completos')]
    recusadas_sem_dados = [r for r in recusadas if not r.get('dados_completos')]
    L = []
    L.append('<!-- ============ TAB 3: ENVIADOS / RECUSADOS ============ -->')
    L.append('<div id="s-enviados" class="sec">')
    L.append('<div class="stitle">Leads Enviados a Brokers</div>')
    if aprovados:
        L.append('<div style="margin-bottom:20px">')
        L.append(f'<div class="stitle" style="color:var(--green);border-left-color:var(--green)">Aprovado \u2014 Cota\u00e7\u00e3o Enviada ao Cliente ({len(aprovados)})</div>')
        L.append('<div class="cards">')
        for e in aprovados:
            L.append(generate_enviados_card_aprovado(e))
        L.append('</div>')
        L.append('</div>')
    if pending_broker:
        L.append('<div style="margin-bottom:20px">')
        L.append(f'<div class="stitle" style="color:#60a5fa;border-left-color:#60a5fa">Enviados ao Broker \u2014 Aguardando Resposta ({len(pending_broker)})</div>')
        L.append('<div class="cards">')
        for e in pending_broker:
            L.append(generate_pending_broker_card(e))
        L.append('</div>')
        L.append('</div>')
    if capitalizacao:
        L.append('<div style="margin-bottom:20px">')
        L.append(f'<div class="stitle" style="color:var(--yellow);border-left-color:var(--yellow)">Capitaliza\u00e7\u00e3o \u2014 Recusados com Dados Completos ({len(capitalizacao)})</div>')
        L.append('<p style="font-size:12px;color:var(--txt2);margin-bottom:12px;padding-left:13px">Leads recusados no seguro fian\u00e7a que possuem dados completos. Candidatos para oferta de seguro de capitaliza\u00e7\u00e3o como alternativa.</p>')
        L.append('<div class="cards">')
        for e in capitalizacao:
            L.append(generate_capitalizacao_card(e))
        L.append('</div>')
        L.append('</div>')
    if invalid_enviados:
        L.append('<div style="margin-bottom:20px">')
        L.append(f'<div class="stitle" style="color:var(--red);border-left-color:var(--red)">CPF Inv\u00e1lido ({len(invalid_enviados)})</div>')
        L.append('<div class="cards">')
        for e in invalid_enviados:
            L.append(generate_enviados_card_invalid(e))
        L.append('</div>')
        L.append('</div>')
    all_recusadas = recusadas  # Show ALL rejected in the collapsible (including capitalização ones)
    if all_recusadas:
        coll_onclick = "var c=this.nextElementSibling;c.classList.toggle('open');this.querySelector('.chv').style.transform=c.classList.contains('open')?'rotate(180deg)':'rotate(0)'"
        L.append(f'<div class="coll-h" onclick="{coll_onclick}">')
        L.append('  <span class="coll-t">Todas as Recusadas pelo Broker</span>')
        L.append(f'  <div style="display:flex;align-items:center;gap:8px"><span class="coll-c">{len(all_recusadas)}</span><span class="chv">\u25bc</span></div>')
        L.append('</div>')
        L.append('<div class="coll-b">')
        L.append('<div class="cards">')
        for e in all_recusadas:
            L.append(generate_enviados_card_recusada(e))
        L.append('</div>')
        L.append('</div>')
    L.append('</div>')
    return '\n'.join(L)


def _priority_badge(prioridade):
    """Return (css_class, full_html) for a priority badge."""
    p = prioridade.strip() if prioridade else 'M\u00e9dia'
    if p.startswith('\u2605') or p == 'TOP' or '\u2605 TOP' in p:
        return ('st-rdy', '<span class="st" style="background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3);font-weight:700">\u2605 TOP</span>')
    elif 'Alta' in p:
        return ('st-imo', f'<span class="st st-imo">{_e(p)}</span>')
    elif 'Baixa' in p:
        return ('st-nao', '<span class="st st-nao">Baixa</span>')
    else:
        return ('st-col', '<span class="st st-col">M\u00e9dia</span>')


def generate_sem_score_row(pos, entry):
    """Generate a single row for the Sem Score table (Tab 4)."""
    nome = entry.get('nome', '')
    profissao = entry.get('profissao', '')
    cpf = entry.get('cpf', '')
    renda = entry.get('renda', '\u2014') or '\u2014'
    aluguel = entry.get('aluguel', '\u2014') or '\u2014'
    doc = entry.get('documentacao', '')
    prioridade = entry.get('prioridade', 'M\u00e9dia')
    if profissao:
        prof_style = 'font-size:11px'
    else:
        profissao = '\u2014'
        prof_style = 'font-size:11px;color:var(--txt2)'
    doc_st = falta_style(doc)
    _, prio_html = _priority_badge(prioridade)
    tr_extra = ''
    td_pos_style = ''
    td_name_style = ''
    if entry.get('top_priority'):
        tr_extra = ' style="border-left:3px solid var(--green)"'
        td_pos_style = ' style="font-weight:700;color:var(--green)"'
        td_name_style = ' style="font-weight:600"'
    L = []
    L.append(f'<tr class="rx"{tr_extra}>')
    L.append(f'  <td{td_pos_style}>{pos}</td>')
    L.append(f'  <td{td_name_style}>{_e(nome)}</td>')
    L.append(f'  <td style="{prof_style}">{_e(profissao)}</td>')
    L.append(f'  <td class="mono">{_e(cpf)}</td>')
    L.append(f'  <td>{_e(renda)}</td>')
    L.append(f'  <td>{_e(aluguel)}</td>')
    L.append(f'  <td style="{doc_st}">{_e(doc)}</td>')
    L.append(f'  <td>{prio_html}</td>')
    L.append('</tr>')
    return '\n'.join(L)


def generate_sem_score_tab(pendente):
    """Generate Tab 4: Sem Score table."""
    L = []
    L.append('<!-- ============ TAB 4: SEM SCORE ============ -->')
    L.append('<div id="s-baixo" class="sec">')
    L.append('<div class="stitle">CPFs Aguardando Consulta de Cr\u00e9dito</div>')
    L.append('<p style="font-size:12px;color:var(--txt2);margin-bottom:16px">Leads que compartilharam CPF mas ainda n\u00e3o tiveram consulta de cr\u00e9dito. Ordenados por renda (maior \u2192 menor).</p>')
    L.append('<table class="tbl">')
    L.append('<thead><tr>')
    L.append('  <th style="width:3%">#</th>')
    L.append('  <th style="width:17%">Nome</th>')
    L.append('  <th style="width:11%">Profiss\u00e3o</th>')
    L.append('  <th style="width:11%">CPF</th>')
    L.append('  <th style="width:9%">Renda</th>')
    L.append('  <th style="width:9%">Aluguel</th>')
    L.append('  <th style="width:27%">Documenta\u00e7\u00e3o</th>')
    L.append('  <th style="width:9%">Prioridade</th>')
    L.append('</tr></thead>')
    L.append('<tbody>')
    for i, entry in enumerate(pendente, 1):
        c = entry.get('comment', '')
        if c:
            L.append(f'<!-- {c} -->')
        L.append(generate_sem_score_row(i, entry))
    L.append('</tbody>')
    L.append('</table>')
    L.append('<p style="font-size:10px;color:var(--txt2);margin-top:8px">\u2605 TOP = dados completos, se score \u2265 400 ser\u00e1 Ready imediatamente. Alta = renda alta ou profiss\u00e3o est\u00e1vel. M\u00e9dia = aguardando mais dados. Baixa = renda baixa ou dados insuficientes.</p>')
    L.append('</div>')
    return '\n'.join(L)


def generate_footer(version, summary_short, broker_names=None):
    """Generate the footer text."""
    if broker_names is None:
        broker_names = 'Arcoseg (Alice) \u00b7 Ittu (Itallo) \u00b7 Darqs (Graziele)'
    L = []
    L.append('<footer>')
    L.append(f'  <p>Lumi Broker CRM \u2014 v{version} \u2014 {_e(summary_short)}</p>')
    L.append(f'  <p>Brokers: {_e(broker_names)}</p>')
    L.append('</footer>')
    return '\n'.join(L)


def generate_js():
    """Generate the tab switching JavaScript."""
    return '<script>\nfunction sw(id,el){\n  document.querySelectorAll(\'.sec\').forEach(s=>s.classList.remove(\'on\'));\n  document.querySelectorAll(\'.tab\').forEach(t=>t.classList.remove(\'on\'));\n  document.getElementById(\'s-\'+id).classList.add(\'on\');\n  el.classList.add(\'on\');\n}\n</script>'


def generate_html(scores, pendente, brokers, config, kpis, version, summary_text):
    """Main entry point. Returns complete HTML string."""
    # Normalize data: ensure 'nome' key exists and broker keys are canonical
    _add_nome(scores)
    _add_nome(pendente)
    brokers = _normalize_brokers(brokers, scores)
    ranking_count = len(scores) + len(pendente) + len(brokers.get('broker_only', [])) + len(brokers.get('invalid_cpfs', []))
    acao_leads = []
    for entry in scores:
        s = entry.get('score', 0)
        st, _ = determine_status(entry)
        if s >= 400 and st == 'Coletar dados':
            acao_leads.append(entry)
    acao_count = len(brokers.get('invalid_cpfs', [])) + len(acao_leads)
    capitalizacao_list = [r for r in brokers.get('recusadas', []) if r.get('dados_completos')]
    enviados_count = len(brokers.get('aprovados', [])) + len(brokers.get('pending_broker', [])) + len(capitalizacao_list) + len(brokers.get('invalid_cpfs_enviados', [])) + len(brokers.get('recusadas', []))
    tab_counts = {'todos': ranking_count, 'acao': acao_count, 'enviados': enviados_count, 'baixo': len(pendente)}
    footer_summary = f'{kpis.get("total_leads", 0)} leads, {kpis.get("cpfs", 0)} CPFs, {kpis.get("verificado", 0)} verificados, {kpis.get("sem_score", 0)} sem score, {kpis.get("cotacao_enviada", 0)} cota\u00e7\u00f5es seguro fian\u00e7a, {kpis.get("capitalizacao", 0)} capitaliza\u00e7\u00e3o'
    broker_names = brokers.get('broker_names', 'Arcoseg (Alice) \u00b7 Ittu (Itallo) \u00b7 Darqs (Graziele)')
    parts = []
    parts.append('<!DOCTYPE html>')
    parts.append('<html lang="pt-BR">')
    parts.append('<head>')
    parts.append('<meta charset="UTF-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    parts.append('<title>Lumi Broker CRM - Gest\u00e3o de Leads Seguro Fian\u00e7a</title>')
    parts.append('<style>')
    parts.append(get_css())
    parts.append('</style>')
    parts.append('</head>')
    parts.append('<body>')
    parts.append('<div class="wrap">')
    parts.append(generate_header(kpis, version, summary_text))
    parts.append(generate_tabs(tab_counts))
    parts.append(generate_ranking_table(scores, pendente, brokers))
    parts.append(generate_acao_tab(scores, brokers))
    parts.append(generate_enviados_tab(brokers))
    parts.append(generate_sem_score_tab(pendente))
    parts.append(generate_footer(version, footer_summary, broker_names))
    parts.append(generate_js())
    parts.append('</body>')
    parts.append('</html>')
    return '\n'.join(parts)


def _load_json(filepath, default=None):
    if default is None:
        default = [] if filepath.endswith('scores.json') or filepath.endswith('pendente.json') else {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f'  [WARN] {filepath} not found')
        return default
    except json.JSONDecodeError as e:
        print(f'  [ERROR] {filepath} invalid JSON: {e}')
        return default


def _create_sample_data(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    scores = [
        {"nome":"Roberto Jesus da Silva","cpf":"739.976.929-04","score":683,"renda":"R$6.000","falta":"Falta: Dados im\u00f3vel","bold_pos":True,"comment":"1. Roberto 683 BOM","details":{"Nascimento":"13/12/1969","Profiss\u00e3o":"Microempreendedor"},"falta_short":"Falta dados im\u00f3vel","falta_items":"Endere\u00e7o \u00b7 CEP \u00b7 Coberturas","nota":"<b>Melhor candidato.</b>","nota_color":"var(--green)"},
        {"nome":"Onivaldo Menegario Sobrinho","cpf":"742.194.648-91","score":399,"renda":"R$7.000","falta":"\u2713 Dados completos","broker_status":"enviado","highlight":True,"comment":"Onivaldo 399 APROVADO"},
        {"nome":"Adilson Modesto Simoes Junior","cpf":"429.816.928-60","score":26,"renda":"R$3.630","falta":"Falta: Conferir dados","comment":"Adilson 26 RUIM"}
    ]
    pendente = [
        {"nome":"Edna Alves dos Santos","cpf":"096.474.664-63","renda":"R$3.800","aluguel":"R$1.200","profissao":"Bab\u00e1","documentacao":"\u2713 Dados quase completos","prioridade":"\u2605 TOP","falta":"\u2713 Dados quase completos","top_priority":True,"comment":"Edna TOP"}
    ]
    brokers = {
        "broker_names":"Arcoseg (Alice) \u00b7 Ittu (Itallo) \u00b7 Darqs (Graziele)",
        "aprovados":[{"nome":"Onivaldo","cpf":"742.194.648-91","score":399,"details":{"Broker":{"text":"Darqs APROVADO","style":"color:var(--green)"}},"nota":"<b>Primeiro aprovado!</b>"}],
        "invalid_cpfs":[{"nome":"Fabiana Pereira","cpf":"032.736.629-07","renda":"R$5.000","profissao":"Manicure","status_bot":"aguardando_cotacao","nota":"Pedir CPF correto."}],
        "invalid_cpfs_enviados":[{"nome":"Fabiana Pereira","cpf":"032.736.629-07","details":{"Renda":"R$5.000"},"nota":"CPF inv\u00e1lido."}],
        "recusadas":[{"nome":"K\u00e1tia da Silva","cpf":"133.776.378-00","details":{"Broker":"Darqs \u2717"}}],
        "broker_only":[{"nome":"K\u00e1tia da Silva","cpf":"133.776.378-00","renda":"R$5.500","falta":"\u2713 Dados completos"}]
    }
    config = {"footer_summary":"Sample test data"}
    for name, data in [('scores.json',scores),('pendente.json',pendente),('brokers.json',brokers),('config.json',config)]:
        with open(os.path.join(data_dir, name), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'  Created sample data in {data_dir}/')
    return scores, pendente, brokers, config


def _build_business_summary(scores, brokers, nb, version):
    """Build a business-focused summary from current data."""
    parts = [f'<b>Status v{version}:</b>']

    # Cotações enviadas (approved with cotacao_enviada=true)
    aprovados = brokers.get('approved', nb.get('aprovados', []))
    cotacao_enviada = [a for a in aprovados if a.get('cotacao_enviada')]
    if cotacao_enviada:
        nomes = ' e '.join(a.get('nome', a.get('name', '?')).split()[0] for a in cotacao_enviada)
        parts.append(f'<span style="color:var(--green)">✅ Cotação seguro fiança enviada a {nomes} — aguardando resposta</span>')

    # Onivaldo special case — re-análise
    for a in aprovados:
        nota = str(a.get('nota', '')).lower()
        if 're-análise' in nota or 'transferida' in nota:
            nome = a.get('nome', a.get('name', '?')).split()[0]
            parts.append(f'<span style="color:var(--orange)">⚠ {nome} — re-análise pendente (corretagem transferida)</span>')

    # Capitalização in progress
    pending = brokers.get('pending_broker', nb.get('pending_broker', []))
    for p in pending:
        if 'capitaliza' in p.get('broker', '').lower():
            nome = p.get('nome', p.get('name', '?')).split()[0]
            parts.append(f'<span style="color:var(--yellow)">📋 {nome} — Capitalização em andamento</span>')

    # Rejected with dados completos — ready for capitalização offer
    recusadas = brokers.get('rejected', nb.get('recusadas', []))
    n_dados_completos = sum(1 for r in recusadas if r.get('dados_completos'))
    if recusadas:
        if n_dados_completos > 0:
            parts.append(f'<span style="color:var(--txt2)">{len(recusadas)} recusadas ({n_dados_completos} com dados completos) — oferecer Título de Capitalização</span>')
        else:
            parts.append(f'<span style="color:var(--txt2)">{len(recusadas)} recusadas — oferecer Título de Capitalização</span>')

    return ' · '.join(parts)


if __name__ == '__main__':
    print('=' * 60)
    print('Lumi Broker CRM \u2014 HTML Generator (Test Mode)')
    print('=' * 60)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, 'data')
    output_path = os.path.join(script_dir, 'index.html')
    paths = [os.path.join(data_dir, n) for n in ['scores.json','pendente.json','brokers.json','config.json']]
    if not all(os.path.exists(p) for p in paths):
        print('\n  JSON data files not found. Creating sample data...')
        scores, pendente, brokers, config = _create_sample_data(data_dir)
    else:
        print(f'\n  Loading data from {data_dir}/')
        scores = _load_json(paths[0], [])
        pendente = _load_json(paths[1], [])
        brokers = _load_json(paths[2], {})
        config = _load_json(paths[3], {})
    # Compute KPIs from actual data
    nb = _normalize_brokers(brokers, scores)
    scored_cpfs = set(re.sub(r'[^\d]', '', s.get('cpf', '')) for s in scores)
    broker_only = [r for r in brokers.get('rejected', nb.get('recusadas', [])) if re.sub(r'[^\d]', '', r.get('cpf', '')) not in scored_cpfs]
    n_invalid = len(brokers.get('invalid_cpf', nb.get('invalid_cpfs', [])))
    n_pending = len(brokers.get('pending_broker', nb.get('pending_broker', [])))
    n_approved = len(brokers.get('approved', nb.get('aprovados', [])))
    n_rejected = len(brokers.get('rejected', nb.get('recusadas', [])))
    n_capitalizacao = sum(1 for r in brokers.get('pending_broker', []) if 'capitaliza' in r.get('broker', '').lower())
    total_cpfs = len(scores) + len(pendente) + len(broker_only) + n_invalid
    version = config.get('version', '8.0')
    # Use tracking data from config for total_leads (auto-update keeps this current)
    total_leads_from_config = config.get('tracking', {}).get('last_leads_row', 279)
    # Dados completos: count from falta field + any approved/pending with complete data
    n_dados_completos = sum(1 for s in scores if '✓ Dados completos' in s.get('falta', '') or s.get('status', '').startswith('Aprovado') or s.get('status', '') == 'Ready ✓')
    n_dados_completos += sum(1 for r in brokers.get('rejected', nb.get('recusadas', [])) if r.get('dados_completos'))
    kpis = {
        'total_leads': total_leads_from_config,
        'cpfs': total_cpfs,
        'dados_completos': n_dados_completos,
        'verificado': len(scores),
        'sem_score': len(pendente),
        'cpf_errado': n_invalid,
        'pending_broker': n_pending,
        'cotacao_enviada': n_approved,
        'capitalizacao': n_capitalizacao,
    }
    summary_text = _build_business_summary(scores, brokers, nb, version)
    print(f'\n  Generating HTML (v{version})...')
    html = generate_html(scores, pendente, brokers, config, kpis, version, summary_text)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    fsize = os.path.getsize(output_path)
    lcount = html.count('\n') + 1
    print(f'\n  Output: {output_path}')
    print(f'  Size: {fsize:,} bytes')
    print(f'  Lines: {lcount:,}')
    print(f'\n  Scores: {len(scores)}')
    print(f'  Pendente: {len(pendente)}')
    nb = _normalize_brokers(brokers, scores)
    print(f'  Ranking total: {len(scores) + len(pendente) + len(nb.get("broker_only", [])) + len(nb.get("invalid_cpfs", []))}')
    print(f'\n  Done. Open {output_path} in a browser to verify.')
