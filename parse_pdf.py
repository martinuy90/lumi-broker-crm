#!/usr/bin/env python3
import re, os, sys, json


def parse_consultation_pdf(pdf_path):
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        if "decrypt" in str(e).lower():
            try:
                reader = PdfReader(pdf_path)
                reader.decrypt("")
            except: return None
        else: return None
    text = ""
    for page in reader.pages:
        try:
            t = page.extract_text()
            if t: text += t + chr(10)
        except: continue
    if not text.strip(): return None
    result = {"pdf_path": pdf_path}
    if "Consulta Pessoas" in text:
        return _parse_vcpe(text, result)
    return _parse_cc(text, result)


def _parse_cc(text, result):
    result["format"] = "centraldaconsulta"
    m = re.search(r"SCORE\s*(\d{1,4})", text)
    if m: result["score"] = int(m.group(1))
    m2 = re.search(r"(?:^|\n)\s*(\d{1,4})\s+\d{3,5}\s+(?:Precisa|Ruim|Bom|Regular)", text)
    if m2 and "score" not in result:
        result["score"] = int(m2.group(1))
    m = re.search(r"Documento Consultado.*?(\d{11})", text, re.DOTALL)
    if m:
        raw = m.group(1)
        result["cpf_raw"] = raw
        result["cpf"] = f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"
    else:
        m = re.search(r"\n(\d{11})\n", text)
        if m:
            raw = m.group(1)
            result["cpf_raw"] = raw
            result["cpf"] = f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"
    m = re.search(r"(\d{7,8})\s+\d{11}\s+(\d{2}/\d{2}/\d{4})", text)
    if m:
        result["consultation_id"] = m.group(1)
        result["consultation_date"] = m.group(2)
    m = re.search(r"RUIM\s*BAIXO\s*REGULAR\s*\n?\s*BOM\s*\n?\s*[^\n]*TIM[^\n]*\n\s*(\w+)", text, re.IGNORECASE)
    if m:
        rt = m.group(1).strip().upper()
        if rt in ("BOM", "REGULAR", "BAIXO", "RUIM"): result["rating"] = rt
        elif "OTIM" in rt: result["rating"] = "OTIMO"
    if "rating" not in result and "score" in result:
        result["rating"] = _score_to_rating(result["score"])
    m = re.search(r"proximos 6 meses\.?\s*\n\s*\n?\s*([A-Z][A-Z\s]+?)\s*\n\s*\d{11}", text)
    if m:
        result["name"] = _clean_name_spaces(m.group(1).strip())
    else:
        m = re.search(r"\n([A-Z][A-Z\s]{5,}?)\s*\n\s*\d{11}", text)
        if m:
            result["name"] = _clean_name_spaces(m.group(1).strip())
    m = re.search(r"Nome da M\w+:\s*\n?\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        mae = m.group(1).strip()
        if mae and len(mae) > 1:
            result["nome_mae"] = _clean_name_spaces(mae)
    m = re.search(r"Data de Nascimento:\s*\n?\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        result["nascimento"] = m.group(1)
    m = re.search(r"RENDA PRESUMIDA\s+POSITIVA:\s*(.*?)$", text, re.IGNORECASE | re.MULTILINE)
    if m:
        result["renda_presumida"] = m.group(1).strip()
    m = re.search(r"(Risco\s+(?:Muito\s+)?(?:Baixo|M.dio|Alto|Moderado)\s+de\s+Inadimpl.ncia)", text, re.IGNORECASE)
    if m:
        result["classificacao"] = m.group(1)
    m = re.search(r"(\d{1,3})%\s*das\s*pessoas", text)
    if m:
        result["probabilidade_pct"] = int(m.group(1))
    return result


def _parse_vcpe(text, result):
    result["format"] = "vcpe"
    m = re.search(r"Score\s*\n?\s*(\d{1,4})\s*/\s*1000", text, re.IGNORECASE)
    if m:
        result["score"] = int(m.group(1))
    all_cpfs = re.findall(r"(\d{3}\.\d{3}\.\d{3}-\d{2})", text)
    for cpf in all_cpfs:
        cpf_raw = re.sub(r"[^\d]", "", cpf)
        if cpf_raw != "39723326884":
            result["cpf"] = cpf
            result["cpf_raw"] = cpf_raw
            break
    m = re.search(r"Nome:\s*\n?\s*([A-Z][A-Z\s\n]+?)(?:\s*CPF:)", text, re.DOTALL)
    if m:
        nm = re.sub(r"\s+", " ", m.group(1).strip())
        result["name"] = _clean_name_spaces(nm)
    if "score" in result:
        result["rating"] = _score_to_rating(result["score"])
    return result


def _score_to_rating(score):
    if score >= 600: return "BOM"
    elif score >= 400: return "REGULAR"
    elif score >= 200: return "BAIXO"
    else: return "RUIM"


def _clean_name_spaces(name):
    name = re.sub(r"\s+", " ", name).strip()
    parts = name.split(" ")
    cleaned = []
    i = 0
    known = {"DA","DE","DO","DAS","DOS","DI","E","A","O","JR"}
    while i < len(parts):
        part = parts[i]
        if len(part) <= 3 and part.upper() not in known:
            if i + 1 < len(parts):
                merged = part + parts[i + 1]
                if merged.isalpha() and len(merged) >= 3:
                    cleaned.append(merged)
                    i += 2
                    continue
            if cleaned:
                merged = cleaned[-1] + part
                if merged.isalpha():
                    cleaned[-1] = merged
                    i += 1
                    continue
        cleaned.append(part)
        i += 1
    return " ".join(cleaned)


def parse_all_pdfs(folder_path):
    results = []
    skipped = []
    for fn in sorted(os.listdir(folder_path)):
        if not fn.endswith(".pdf"): continue
        if not (fn.startswith("Consulta") or fn.startswith("vcpe")): continue
        path = os.path.join(folder_path, fn)
        print(f"  Parsing: {fn}...", end=" ")
        try:
            result = parse_consultation_pdf(path)
        except Exception as e:
            print(f"ERROR: {e}")
            skipped.append((fn, str(e)))
            continue
        if result and "score" in result:
            score = result["score"]
            rating = result.get("rating", "?")
            name = result.get("name", "?")
            print(f"Score {score} {rating} - {name}")
            results.append(result)
        else:
            print("skipped")
            skipped.append((fn, "no score"))
    return results


def deduplicate_results(results):
    by_cpf = {}
    no_cpf = []
    for r in results:
        cpf = r.get("cpf_raw")
        if not cpf:
            no_cpf.append(r)
            continue
        if cpf not in by_cpf:
            by_cpf[cpf] = r
        else:
            existing = by_cpf[cpf]
            eid = int(existing.get("consultation_id", "0"))
            nid = int(r.get("consultation_id", "0"))
            if nid > eid: by_cpf[cpf] = r
    return list(by_cpf.values()) + no_cpf


if __name__ == "__main__":
    folder = "/Users/martincoulthurst/Desktop/Lumi Ai/Consultas"
    if len(sys.argv) > 1:
        pdf = sys.argv[1]
        if not os.path.exists(pdf):
            print(f"Not found: {pdf}")
            sys.exit(1)
        result = parse_consultation_pdf(pdf)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Could not parse")
    else:
        print(f"Scanning: {folder}/")
        results = parse_all_pdfs(folder)
        unique = deduplicate_results(results)
        unique.sort(key=lambda x: x.get("score", 0), reverse=True)
        print(f"Parsed {len(results)} PDFs, {len(unique)} unique")
        for i, r in enumerate(unique, 1):
            s = r.get("score", "?")
            rt = r.get("rating", "?")
            nm = r.get("name", "?")
            cp = r.get("cpf", "?")
            print(f"{i:3} {s:>4} {rt:8} {cp:16} {nm}")
        # Verification
        known = {
            "08138579960": ("Daiane", 462),
            "73997692904": ("Roberto", 683),
            "40074107801": ("Stephanie", 182),
            "14498630602": ("Thaiara", 451),
        }
        ok = True
        for cpf_raw, (name, expected) in known.items():
            found = next((r for r in unique if r.get("cpf_raw") == cpf_raw), None)
            if found:
                actual = found.get("score")
                st = "PASS" if actual == expected else "FAIL"
                if st == "FAIL": ok = False
                print(f"  {st}: {name} expected={expected} got={actual}")
            else:
                ok = False
                print(f"  FAIL: {name} not found")
        print("ALL PASSED" if ok else "FAILURES")
        output = os.path.join(folder, "parsed_results.json")
        with open(output, "w", encoding="utf-8") as f:
            json.dump(unique, f, indent=2, ensure_ascii=False)
        print(f"Saved: {output}")
