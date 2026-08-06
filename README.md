
# GEO Auditor

> A framework for evaluating how well websites are optimized for Generative Engine Optimization (GEO) using a combination of deterministic analysis and LLM-based semantic evaluation.

---

# Overview

GEO Auditor crawls a website, constructs a Canonical Website Representation (CWR), evaluates it across multiple GEO dimensions, and produces a weighted GEO score together with a detailed audit report.

The framework is designed around two principles:

- Every evaluation criterion should be independently measurable.
- LLMs should only receive structured, relevant information instead of raw HTML.

---

# Getting Started

The project consists of two repositories:

- **Backend (this repository)** – GEO crawling, evaluation, scoring, and report generation.
- **Frontend** – User interface for submitting websites and viewing audit reports.

## Backend Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create environment variables

Copy the example environment file.

```bash
cp .env.example .env
```

Update the values as required.

### 3. Run the backend

```bash
python app/main.py
```

The backend will start locally and expose the GEO audit API.

---

## Frontend Setup

Frontend repository:

**https://github.com/haideraqeeb/geo-audit-frontend**

### 1. Clone the frontend repository

```bash
git clone https://github.com/haideraqeeb/geo-audit-frontend.git
cd geo-audit-frontend
```

### 2. Create environment variables

```bash
cp .env.example .env
```

Configure the backend API URL if necessary.

### 3. Install dependencies

```bash
npm install
```

### 4. Start the development server

```bash
npm run dev
```

The frontend will connect to the locally running backend and provide the GEO audit interface.

---

# Architecture

<p align="center">
  <img src="assets/architecture.png" alt="App Architecture" width="200">
</p>


---

# Research

The framework is built around GEO techniques that consistently appear across GEO research and established Search Central guidance.

## Final List of Important Techniques

| Technique | Relative Importance |
|------------|--------------------:|
| Citations to authoritative sources | 5 |
| Evidence-backed quantitative claims | 5 |
| Authoritative quotations | 5 |
| Readability | 4 |
| Entity richness | 4 |
| Schema.org (JSON-LD) | 4 |
| Freshness | 4 |
| User intent coverage | 3 |
| Internal linking | 3 |
| Meta tags | 3 |
| Robots.txt & Sitemap | 3 |
| llms.txt | 2 |

## Category Weights

### Trust & Authority (40%)

- Citation authority
- Evidence-backed quantitative claims

### Content Quality (35%)

- Readability
- Entity richness
- Freshness
- User intent coverage

### Technical Discoverability (25%)

- Schema.org (JSON-LD)
- Internal linking
- Robots.txt & Sitemap
- Meta tags
- llms.txt

---

# System Design

## What is sent to the LLM?

Instead of sending raw HTML, the crawler converts everything into a structured JSON representation.

Possible inputs include:

- Structured page content
- Internal & external links
- Metadata
- Schema.org / JSON-LD
- HTTP metadata
- Crawl resources (robots.txt, sitemap, llms.txt)

Every evaluator receives only the subset of data it requires.

---

# Canonical Website Representation (CWR)

The crawler builds a single normalized JSON object containing:

- Website information
- Page content
- Links
- Metadata
- Structured data
- Crawl resources
- Temporal information

## Crawl Constraints

- Maximum depth: 2–3
- Maximum pages: 40
- Maximum representation: ~80k tokens
- Token counting using tiktoken
- Stay within the same domain

(The JSON schema from the design document should be inserted here.)

---

# Evaluation Framework

Eight independent evaluators operate on the CWR.

| Evaluator | Primary Input |
|-----------|---------------|
| Citation Authority | Paragraphs, External Links |
| Evidence Support | Paragraphs, Tables |
| Readability | Headings, Paragraphs, Lists |
| Entity Coverage | Title, Headings, Paragraphs |
| Freshness | Dates, Content, Schema, Headers |
| User Intent Coverage | Content |
| Structured Data | JSON-LD |
| Technical Discoverability | robots.txt, sitemap, metadata, llms.txt |

## Semantic vs Deterministic

### Semantic

- Citation Authority
- Evidence Support
- Readability
- Entity Coverage
- Freshness
- User Intent Coverage

### Deterministic

- Structured Data
- Technical Discoverability

Each evaluator uses an operational rubric instead of a generic scoring prompt.

---

# Scoring Algorithm

The scoring system is criteria-based and additive.

Evaluator outputs are weighted according to research importance before being aggregated into category scores.

The framework also computes evaluator confidence, category confidence, and overall confidence.

(Scoring equations from the design document should be included here.)

---

# Report Structure

The generated report is layered.

### Layer 1

- Overall GEO Score

### Layer 2

- Trust & Authority
- Content Quality
- Technical Discoverability

### Layer 3

- Individual evaluator findings
- Supporting evidence
- Recommendations

---

# Evaluator Output

Every evaluator returns a common schema consisting of:

- Score
- Confidence
- Summary
- Findings
- Evidence
- Recommendations
- Metadata

This enables all evaluators to plug into the same scoring pipeline.

---

# Performance Considerations

- Prompt caching
- Parallel evaluator execution
- Token budgeting
- Crawl limits
- Domain restriction
- Structured inputs to reduce token usage

---

# Implementation Pipeline

1. Crawl website
2. Build Canonical Website Representation
3. Run deterministic checks
4. Run semantic evaluators
5. Aggregate weighted scores
6. Compute confidence
7. Generate layered GEO report
