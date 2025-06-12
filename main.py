# -*- coding: utf-8 -*-
"""PrivChat‑API (no confidence version)"""

import logging
import re
import sys
import time
from typing import List, Dict

import requests
import spacy
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ───────── SETTINGS ─────────
MODEL_NAME = "en_core_web_sm"
OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_CHAT_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_MODEL_PREFS = ["tinyllama:latest", "tinyllama:1.1b"]
OLLAMA_TIMEOUT = 300
OLLAMA_PULL_TIMEOUT = 600

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(asctime)s — %(message)s")

# ───────── spaCy ─────────
try:
    nlp = spacy.load(MODEL_NAME)
except OSError:
    raise SystemExit(
        f"[!] spaCy model '{MODEL_NAME}' not found.\n"
        "    Install with:  python -m spacy download en_core_web_sm"
    )

# ───────── Ollama helpers ─────────
def _model_present(tag: str, models: List[dict]) -> bool:
    return any(m.get("name") == tag for m in models)

def ensure_ollama_model(tag: str):
    try:
        models = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10).json().get("models", [])
        if _model_present(tag, models):
            logging.info(f"Ollama model '{tag}' already present.")
            return
        logging.info(f"Ollama model '{tag}' missing → pulling…")
        requests.post(
            f"{OLLAMA_HOST}/api/pull", json={"name": tag}, timeout=OLLAMA_PULL_TIMEOUT
        ).raise_for_status()
        for _ in range(12):
            time.sleep(5)
            models = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10).json().get("models", [])
            if _model_present(tag, models):
                logging.info(f"Model '{tag}' is ready.")
                return
        raise RuntimeError(f"Model '{tag}' still not listed after pull.")
    except Exception as e:
        raise RuntimeError(f"Unable to pull '{tag}': {e}")

ACTIVE_MODEL = None
for tag in OLLAMA_MODEL_PREFS:
    try:
        ensure_ollama_model(tag)
        ACTIVE_MODEL = tag
        break
    except RuntimeError as err:
        logging.warning(err)
if ACTIVE_MODEL is None:
    logging.critical("No TinyLLaMA model available — aborting.")
    sys.exit(1)
logging.info(f"⚡ Using Ollama model → {ACTIVE_MODEL}")

# ───────── FastAPI APP ─────────
app = FastAPI(title="PrivChat-API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Prompt(BaseModel):
    prompt: str

# ───────── PII Patterns ─────────
PII_REGEX_PATTERNS: Dict[str, re.Pattern] = {
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "PHONE": re.compile(r"\b(?:\+?91[\- ]?)?[6-9]\d{9}\b"),
    "ID_PAN": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "ID_AADHAAR": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "ID_PASSPORT": re.compile(r"\b[A-PR-WY][0-9]{7}\b", re.I),
    "DL_NUMBER": re.compile(r"\b[A-Z]{1,2}-?\d{2}\d{11}\b"),
    "CARD_NUMBER": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "BANK_ACCOUNT": re.compile(r"account number(?:\sis)?\b\d{9,18}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "STUDENT_ID": re.compile(r"\b\d{4}[A-Z]{2}\d{4}\b"),
    "VEHICLE_REG": re.compile(r"\b[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}\b"),
    "IP_ADDRESS": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    "BLOOD_GROUP": re.compile(r"\b(?:A|B|AB|O)[+-]\b"),
    "CARD_SUFFIX": re.compile(r"ending(?:\sin)?\s(\d{4})"),
}

LABEL_PRIORITY = {
    "ID_PAN": 100,
    "ID_AADHAAR": 100,
    "SSN": 100,
    "ID_PASSPORT": 95,
    "DL_NUMBER": 95,
    "CARD_NUMBER": 90,
    "PHONE": 80,
    "EMAIL": 80,
    "VEHICLE_REG": 70,
    "BANK_ACCOUNT": 60,
    "STUDENT_ID": 60,
    "CARD_SUFFIX": 55,
    "IP_ADDRESS": 50,
    "BLOOD_GROUP": 40,
}

# ───────── Detection & Utilities ─────────
def regex_entities(text: str):
    ents = []
    for label, rx in PII_REGEX_PATTERNS.items():
        for m in rx.finditer(text):
            ents.append({"text": m.group(), "label": label, "start": m.start(), "end": m.end()})
    return ents

def is_bank_context(text: str, span_start: int) -> bool:
    left_ctx = text[max(0, span_start - 20): span_start].lower()
    return any(k in left_ctx for k in ["account", "a/c", "acct", "acc", "bank"])

def postprocess_entities(ents: List[dict], text: str) -> List[dict]:
    for match in PII_REGEX_PATTERNS["CARD_SUFFIX"].finditer(text):
        span_text = match.group(1)
        ents.append({
            "text": span_text,
            "label": "CARD_SUFFIX",
            "start": match.start(1),
            "end": match.end(1),
        })

    for e in ents:
        if e["label"] == "ORG":
            prefix = text[max(0, e["start"] - 5): e["start"]]
            if re.search(r"\b(?:dr|mr|mrs|ms)\.?\s*$", prefix, re.I):
                e["label"] = "PERSON"

    for e in ents:
        if e["label"] == "BANK_ACCOUNT" and len(e["text"]) == 10:
            if re.fullmatch(PII_REGEX_PATTERNS["PHONE"], e["text"]):
                e["label"] = "PHONE"
        if e["label"] == "BANK_ACCOUNT" and not is_bank_context(text, e["start"]):
            continue

    ents.sort(key=lambda x: (x["start"], -LABEL_PRIORITY.get(x["label"], 1)))
    result = []
    for ent in ents:
        if any(max(ent["start"], r["start"]) < min(ent["end"], r["end"]) for r in result):
            continue
        result.append(ent)
    return result

def sanitize_prompt(text: str, ents: List[dict]) -> str:
    for e in sorted(ents, key=lambda x: x["start"], reverse=True):
        text = text[: e["start"]] + f"[[{e['label']}]]" + text[e["end"] :]
    return text

def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

def highlight(text: str, ents: List[dict]):
    if not ents:
        return html_escape(text)
    ents = sorted(ents, key=lambda e: e["start"])
    out, last = [], 0
    for e in ents:
        out.append(html_escape(text[last : e["start"]]))
        tooltip = f"{e['label']}"
        out.append(
            f"<mark title='{tooltip}' data-label='{e['label']}'>"
            f"{html_escape(e['text'])}</mark>"
        )
        last = e["end"]
    out.append(html_escape(text[last:]))
    return "".join(out)

@app.post("/process")
def process(req: Prompt):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Prompt must not be empty")

    doc = nlp(prompt)
    spacy_ents = [
        {
            "text": ent.text,
            "label": ent.label_,
            "start": ent.start_char,
            "end": ent.end_char,
        }
        for ent in doc.ents
        if ent.label_ != "DATE"
    ]
    regex_ents = regex_entities(prompt)
    ents = postprocess_entities(spacy_ents + regex_ents, prompt)

    highlighted = highlight(prompt, ents)
    safe_prompt = sanitize_prompt(prompt, ents)

    try:
        r = requests.post(
            OLLAMA_CHAT_URL,
            json={"model": ACTIVE_MODEL, "messages": [{"role": "user", "content": safe_prompt}], "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        r.raise_for_status()
        llm_text = (
            r.json().get("message", {}).get("content", "").strip()
            or "⚠️ LLM returned an empty response"
        )
    except requests.RequestException as e:
        llm_text = f"⚠️ LLM error: {e}"

    return {
        "entities": [{"text": e["text"], "label": e["label"]} for e in ents],
        "highlighted_text": highlighted,
        "llm_response": llm_text,
        "pii_detected": bool(ents),
    }
