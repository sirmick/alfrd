# AI Document Secretary - Build Plan

## Core Concept
Personal document management system that ingests any document type, extracts structured data via AI, and maintains hierarchical summaries (weekly → monthly → yearly) organized by category.

## Architecture
```
Documents → AI Processing → Structured Storage → Hierarchical Summaries → MCP Server Interface
```

**Key Components:**
1. **Input**: File upload (later: mobile scan, email)
2. **Processing**: LLM extracts facts, categorizes, summarizes per document type
3. **Storage**: 
   - Raw documents (filesystem)
   - Structured facts (SQLite with JSON)
   - Running summaries (markdown files by category: bills.md, taxes.md, etc.)
4. **Aggregation**: Weekly → Monthly → Yearly rollups
5. **Interface**: MCP server with query/action tools (CSV manipulation, calculations, etc.)

## MVP - Phase 1 (Start Here)
Build a working prototype YOU use daily:

**Features:**
- Watch a folder for new PDFs/images
- Process with Claude API (vision + text extraction)
- Categorize documents (bill, tax, receipt, insurance, advertising, other)
- Extract structured data (vendor, amount, due date, key facts)
- Store in SQLite
- Generate weekly summary markdown
- Simple CLI to query: "What bills are due?" "Total spent on utilities?"

**Tech Stack:**
- Python
- Claude API (Sonnet 4.5)
- SQLite
- Local filesystem
- CLI interface

## Immediate Next Steps

1. **Set up project structure:**
```
document-secretary/
├── processor.py          # Core document processing
├── database.py          # SQLite wrapper
├── summarizer.py        # Generate rollup summaries
├── cli.py              # Command interface
├── config.py           # API keys, paths
├── documents/          # Raw document storage
├── summaries/          # Generated markdown files
└── data.db            # SQLite database
```

2. **Build core loop (first 2 hours):**
   - Initialize SQLite schema
   - Process single document with Claude API
   - Store extracted data
   - Generate basic summary

3. **Test with your own documents for 1 month** - if you don't use it daily, pivot

## Later Phases
- Phase 2: Web UI, better categorization, running totals
- Phase 3: Mobile apps, email ingestion, multi-user

## Business Model (After Validation)
- Start with technical users (open source MCP core)
- Hosted version: $20-50/month
- Consumer apps: Lower price point
- Target: $5K MRR in 12-18 months

---

**Now go build the document processor. Start with getting one document processed and stored correctly.**
