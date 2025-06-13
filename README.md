# PrivChat-PII-Detection

# PrivChat – PII Detection + LLM Response

## 🔍 Overview

PrivChat is a privacy-focused chatbot API that:

- Detects Personally Identifiable Information (PII) using both regex and spaCy.
- Highlights detected entities in a frontend UI.
- Sends sanitized prompts to a local LLM via Ollama for secure responses.
- Displays LLM responses and visual indicators of PII detection.

---

## ⚙️ Features

- ✅ PII entity recognition using combined regex + spaCy NER  
- ✅ Post-processing to disambiguate overlapping/conflicting entities  
- ✅ Entity highlighting and tooltip-based UI  
- ✅ LLM inference through locally running TinyLLaMA (`tinyllama:1.1b`)  
- ✅ Date & IP detection with contextual correction  
- ✅ Regex-based sanitization before LLM query  

---

## 🧱 Tech Stack

- **Backend**: FastAPI + spaCy + Regex  
- **LLM Engine**: Ollama + TinyLLaMA (`tinyllama:1.1b`)  
- **Frontend**: Vanilla JS + HTML + CSS  
- **Deployment**: Localhost  

---

## 🚀 Setup Instructions

### Prerequisites

- Python 3.8+  
- Ollama with `tinyllama:1.1b` model pulled  
- spaCy model installed  

### Installation

```bash
pip install fastapi uvicorn requests spacy
python -m spacy download en_core_web_sm

### Running the API

```bash
uvicorn app:app --reload --port 8000



