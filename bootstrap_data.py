#!/usr/bin/env python3
"""
bootstrap_data.py - Parse the Lumi Broker CRM index.html and generate structured JSON data files.

Extracts data from:
  1. Tab 1 ranking table (scored leads, PENDENTE leads, broker-only, invalid CPF rows)
  2. Tab 3 enviados/recusados cards
  3. Tab 4 sem score table

Generates:
  data/scores.json    - 49 scored leads
  data/pendente.json  - 21 PENDENTE leads (from Tab 4 table)
  data/brokers.json   - approved, rejected, invalid_cpf
  data/config.json    - configuration and tracking
"""

import json
import os
import re
from html.parser import HTMLParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(SCRIPT_DIR, "index.html")
DATA_DIR = os.path.join(SCRIPT_DIR, "data")


class TableRowParser(HTMLParser):
    """Extract <tr> rows from an HTML table body."""

    def __init__(self):
        super().__init__()
        self.rows = []
        self._in_tr = False
        self._in_td = False
        self._in_thead = False
        self._current_row = None
        self._current_cell = ""
        self._in_badge = False
        self._badge_text = ""
        self._in_st = False
        self._st_text = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "thead":
            self._in_thead = True
        elif tag == "tr" and not self._in_thead:
            self._in_tr = True
            self._current_row = {
                "class": d.get("class", ""),
                "style": d.get("style", ""),
                "cells": [],
                "badge": "",
                "status": "",
            }
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._current_cell = ""
        elif tag == "span" and self._in_td:
            cls = d.get("class", "")
            if "badge" in cls:
                self._in_badge = True
                self._badge_text = ""
            elif "st" in cls.split():
                self._in_st = True
                self._st_text = ""

    def handle_endtag(self, tag):
        if tag == "thead":
            self._in_thead = False
        elif tag == "tr" and self._in_tr:
            self._in_tr = False
            if self._current_row and self._current_row["cells"]:
                self.rows.append(self._current_row)
            self._current_row = None
        elif tag == "td" and self._in_td:
            self._in_td = False
            if self._current_row is not None:
                self._current_row["cells"].append(self._current_cell.strip())
        elif tag == "span":
            if self._in_badge:
                self._in_badge = False
                if self._current_row is not None:
                    self._current_row["badge"] = self._badge_text.strip()
            if self._in_st:
                self._in_st = False
                if self._current_row is not None:
                    self._current_row["status"] = self._st_text.strip()

    def handle_data(self, data):
        if self._in_badge:
            self._badge_text += data
        if self._in_st:
            self._st_text += data
        if self._in_td:
            self._current_cell += data


def extract_section(html, section_id):
    """Extract the content of a <div id='s-...'> section."""
    pattern = r'<div id="s-' + section_id + r'"[^>]*>(.*?)(?=<div id="s-|<footer)'
    m = re.search(pattern, html, re.DOTALL)
    return m.group(0) if m else ""


def cpf_from_text(text):
    m = re.search(r'(\d{3}\.\d{3}\.\d{3}-\d{2})', text)
    return m.group(1) if m else ""


def score_from_text(text):
    m = re.search(r'Score\s+(\d+)', text)
    return int(m.group(1)) if m else None


def parse_ranking_table(html):
    section = extract_section(html, "todos")
    table_m = re.search(r'<table class="tbl">(.*?)</table>', section, re.DOTALL)
    if not table_m:
        print("ERROR: Could not find ranking table")
        return [], [], [], []

    parser = TableRowParser()
    parser.feed(table_m.group(0))

    scored, pendente, broker_only, invalid_cpf = [], [], [], []

    for row in parser.rows:
        cells = row["cells"]
        badge = row["badge"]
        status = row["status"]
        row_class = row["class"].strip()
        row_style = row["style"].strip()

        if len(cells) < 8:
            continue

        name = cells[1].strip()
        cpf = cells[2].strip()
        score_text = cells[3].strip()
        renda = cells[5].strip()
        falta = cells[6].strip()

        if "INV" in badge and "LIDO" in badge or "rgba(239,68,68,.1)" in row_style:
            invalid_cpf.append({
                "name": name, "cpf": cpf,
                "renda": renda if renda != "\u2014" else "",
                "falta": falta, "status": status,
            })
        elif badge == "RECUSADA":
            broker_only.append({
                "name": name, "cpf": cpf, "score": score_text,
                "renda": renda, "falta": falta, "status": status,
                "row_class": row_class,
            })
        elif badge == "PENDENTE":
            pendente.append({
                "name": name, "cpf": cpf, "renda": renda,
                "falta": falta, "status": status, "row_class": row_class,
            })
        else:
            try:
                sv = int(score_text)
            except ValueError:
                sv = score_text
            scored.append({
                "name": name, "cpf": cpf, "score": sv,
                "rating": badge, "renda": renda, "falta": falta,
                "status": status, "row_class": row_class,
            })

    return scored, pendente, broker_only, invalid_cpf


def parse_sem_score_table(html):
    section = extract_section(html, "baixo")
    table_m = re.search(r'<table class="tbl">(.*?)</table>', section, re.DOTALL)
    if not table_m:
        print("ERROR: Could not find sem score table")
        return []

    parser = TableRowParser()
    parser.feed(table_m.group(0))

    results = []
    for row in parser.rows:
        cells = row["cells"]
        if len(cells) < 8:
            continue
        prof = cells[2].strip()
        if prof == "\u2014":
            prof = ""
        results.append({
            "name": cells[1].strip(),
            "cpf": cells[3].strip(),
            "renda": cells[4].strip(),
            "profissao": prof,
            "aluguel": cells[5].strip(),
            "falta": cells[6].strip(),
            "prioridade": row["status"].strip(),
        })
    return results


def extract_card_fields(card_html):
    """Extract name, subtitle, and key-value fields from a card HTML fragment."""
    nm = re.search(r'<div class="crd-n">(.*?)</div>', card_html)
    sm = re.search(r'<div class="crd-sub"[^>]*>(.*?)</div>', card_html)
    fields = {}
    for fm in re.finditer(
        r'<span class="l">(.*?)</span><span class="v"[^>]*>(.*?)</span>',
        card_html
    ):
        fields[fm.group(1).strip().rstrip(":")] = fm.group(2).strip()
    name = nm.group(1).strip() if nm else ""
    sub = sm.group(1).strip() if sm else ""
    return name, sub, fields


def parse_enviados(html):
    section = extract_section(html, "enviados")

    approved = []
    rejected = []
    invalid_cpf = []

    # --- APPROVED ---
    app_m = re.search(
        r'Aprovado.*?<div class="crd crd-gl"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        section, re.DOTALL
    )
    if app_m:
        text = app_m.group(0)
        name, sub, fields = extract_card_fields(text)
        if name and sub:
            cpf = cpf_from_text(sub)
            score = score_from_text(sub)
            broker_text = fields.get("Broker", "")
            broker = "Darqs" if "Darqs" in broker_text else ""
            insurer = "Porto Seguro" if "Porto Seguro" in broker_text else ""
            approved.append({
                "name": name, "cpf": cpf, "score": score,
                "broker": broker, "insurer": insurer,
                "valor": fields.get("Valor", ""),
                "vigencia": fields.get("Vig\u00eancia", ""),
            })

    # --- INVALID CPF (Tab 3 only has Fabiana card) ---
    inv_m = re.search(
        r'CPF Inv.*?<div class="crd crd-rl"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        section, re.DOTALL
    )
    if inv_m:
        text = inv_m.group(0)
        name, sub, fields = extract_card_fields(text)
        if name and sub:
            cpf = cpf_from_text(sub)
            entry = {"name": name, "cpf": cpf}
            if fields.get("Renda"):
                entry["renda"] = fields["Renda"]
            if fields.get("Telefone"):
                entry["phone"] = fields["Telefone"]
            invalid_cpf.append(entry)

    # --- REJECTED (6 cards inside collapsible coll-b) ---
    # Find the coll-b container that holds the rejected cards
    coll_start = section.find('<div class="coll-b">')
    if coll_start >= 0:
        rest = section[coll_start:]
        # Find all crd-rl card start positions
        starts = [m.start() for m in re.finditer(r'<div class="crd crd-rl"', rest)]
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(rest)
            card = rest[start:end]
            name, sub, fields = extract_card_fields(card)
            if name and sub:
                cpf = cpf_from_text(sub)
                score = score_from_text(sub)
                pf = fields.get("Profiss\u00e3o", "")
                profissao, renda = "", ""
                if " \u00b7 " in pf:
                    parts = pf.split(" \u00b7 ", 1)
                    profissao, renda = parts[0].strip(), parts[1].strip()
                elif pf:
                    profissao = pf.strip()
                entry = {
                    "name": name, "cpf": cpf,
                    "profissao": profissao, "renda": renda,
                    "broker_notes": fields.get("Broker", ""),
                }
                if score is not None:
                    entry["score"] = score
                rejected.append(entry)

    return approved, rejected, invalid_cpf


def generate_config():
    return {
        "version": "7.0",
        "google_sheet_id": "1AuW-FQKAOIpb-BAkZqmbfejeTn98qhgCm8HlhWH5Cgo",
        "gids": {"leads": "0", "dashboard_dados": "739841676", "historico": "2069959500"},
        "cofounders_phones": ["59899143298", "5521964436960"],
        "cofounders_names": ["Martin Coulthurst", "Bernardo Precht", "Elisa Pereira", "Martin Cultru"],
        "score_thresholds": {"bom": 600, "regular": 400, "baixo": 200},
        "tracking": {"last_leads_row": 251, "last_historico_row": 4240, "last_dashboard_dados_row": 224},
    }


def main():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    os.makedirs(DATA_DIR, exist_ok=True)

    scored, pendente_ranking, broker_only, invalid_ranking = parse_ranking_table(html)
    pendente = parse_sem_score_table(html)
    approved, rejected, invalid_cpf = parse_enviados(html)

    # Merge invalid CPFs: Tab 3 card has Fabiana; ranking table has both Fabiana & Bruna
    inv_cpfs_found = {e["cpf"] for e in invalid_cpf}
    for ir in invalid_ranking:
        if ir["cpf"] not in inv_cpfs_found:
            entry = {"name": ir["name"], "cpf": ir["cpf"]}
            if ir.get("renda"):
                entry["renda"] = ir["renda"]
            invalid_cpf.append(entry)

    brokers = {"approved": approved, "rejected": rejected, "invalid_cpf": invalid_cpf}
    config = generate_config()

    def write_json(filename, data):
        p = os.path.join(DATA_DIR, filename)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  Written: {p}")

    write_json("scores.json", scored)
    write_json("pendente.json", pendente)
    write_json("brokers.json", brokers)
    write_json("config.json", config)

    print()
    print("=" * 50)
    print("VERIFICATION")
    print("=" * 50)

    checks = [
        ("scores.json", len(scored), 49),
        ("pendente.json", len(pendente), 21),
        ("brokers approved", len(approved), 1),
        ("brokers rejected", len(rejected), 6),
        ("brokers invalid_cpf", len(invalid_cpf), 2),
    ]

    all_ok = True
    for label, actual, expected in checks:
        ok = actual == expected
        if not ok:
            all_ok = False
        status = "OK" if ok else f"MISMATCH (expected {expected})"
        print(f"  {label}: {actual} entries {status}")

    print(f"  config.json: valid JSON OK")
    print()
    print("Cross-reference (ranking table):")
    print(f"  PENDENTE rows in ranking: {len(pendente_ranking)}")
    print(f"  RECUSADA rows in ranking: {len(broker_only)}")
    print(f"  INVALIDO rows in ranking: {len(invalid_ranking)}")
    print()

    if all_ok:
        print("ALL COUNTS MATCH -- bootstrap complete!")
    else:
        print("SOME COUNTS DO NOT MATCH -- review output above.")

    # Print sample entries for quick spot-check
    print()
    print("--- Sample: scores.json[0] ---")
    print(json.dumps(scored[0], ensure_ascii=False, indent=2))
    print()
    print("--- Sample: pendente.json[0] ---")
    print(json.dumps(pendente[0], ensure_ascii=False, indent=2))
    print()
    print("--- Sample: brokers.json approved[0] ---")
    print(json.dumps(approved[0], ensure_ascii=False, indent=2))
    print()
    print("--- Sample: brokers.json rejected[0] ---")
    if rejected:
        print(json.dumps(rejected[0], ensure_ascii=False, indent=2))

    return 0 if all_ok else 1


if __name__ == "__main__":
    exit(main())
