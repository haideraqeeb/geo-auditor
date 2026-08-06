# geo plan


firstly we will collect data from the website link which is provided
- we crawl the website
- then we build a canonical website representation

now this has to be done for a few pages, lets say we give a page and then based on this page the user has to find more pages
we will define a crawler but it is going to have some borundaries

- max depth of 2 or 3
- maximum pages of 40
- maximum tokens(in the representation) of around 80k, use tiktoken for this
- not be able to go to a different domain

now after we have collected the pages, we have to create the cwr

we collect data from the following sources
- website pages
- meta tags(extract)
- llms.txt(if present, just add like +2 for this, do not consider alot)

---

input shape(cwr)

```json
{
  "website": {
    "url": "https://openai.com",
    "domain": "openai.com",
    "language": "en"
  },

  "content": [
    {
      "type": "page",
      "url": "https://openai.com/",
      "title": "OpenAI",
      "content": "..."
    },
    {
      "type": "page",
      "url": "https://openai.com/api",
      "title": "OpenAI API",
      "content": "..."
    }
  ], // All textual content from crawled pages

  "links": {
    "internal": [
      "https://openai.com/api",
      "https://openai.com/chatgpt",
      "https://openai.com/research"
    ],

    "external": [
      "https://arxiv.org/...",
      "https://platform.openai.com/docs"
    ]
  },

  "metadata": [
    {
      "url": "https://openai.com/",

      "title": "...",

      "description": "...",

      "canonical": "...",

      "robots": "...",

      "open_graph": {},

      "twitter": {}
    }
  ],

  "structured_data": [
    {
      "url": "https://openai.com/",

      "schema": [
        {
          "@type": "Organization"
        },
        {
          "@type": "WebSite"
        }
      ]
    }
  ],

  "crawl_resources": {
    "robots_txt": {
      "exists": true,
      "content": "..."
    },

    "sitemap": {
      "exists": true,
      "urls": [
        "...",
        "...",
        "..."
      ]
    },

    "llms_txt": {
      "exists": false,
      "content": null
    }
  },

  "temporal": [
    {
      "url": "https://openai.com/",

      "published": "...",

      "modified": "...",

      "last_modified_header": "..."
    }
  ],

}
```

there are going to be different evaluators

1. citation authority evaluator
2. evidence support evaluator
3. readability evaluator
4. entity coverage evaluator
5. freshness evaluator(mixed appraoch)
6. FAQ/user intent evaluator
7. structured data evaluator(deterministic)
8. technical discoverability evaluator(deterministic)

these are going to based on the following descriptions

1. citation authority evaluator

input

```
content
```

evaluates

- authoritative citations
- citation coverage
- credibility

score

0-5

---

2. evidence support evaluator

input

```
content
```

find

- numbers
- percentages
- benchmarks
- measurements

evaluate

Are they supported?

Score

0-5

---

3. readability evaluator

input

```
content
```

rvaluate

- clarity
- chunking
- accessibility

---

4. rntity coverage evaluator

input

```
content
```

rvaluate

- important entities
- terminology
- topic completeness

---

5. freshness evaluator

input

```
metadata
```

evaluate

- updated recently
- outdated references
- stale information

hybrid result for this
---

6. faq / user intent evaluator

input 
```
content
```

here we are evaluating
> Does this page answer the questions users or LLMs are likely to have?

a page can score perfectly without an actual faq section if it naturally covers those questions

---

7. structured data evaluator(deterministic)

input

```
json-ld
```

evaluate

- correct type
- completeness
- relevance
- implementation quality

---

8. technical discoverability evaluator(deterministic)

input

```
robots.txt

sitemap

meta

llms.txt
```

this one actually doesn't need much semantic reasoning, its mainly
- completeness
- correctness
- best practices

---

now, for each and every evaluator, we will have its separate rubric in its prompt so that it can understand what it has to and then do it

it is better to have the rubric as an operational rubric instead of having a rubric which is just gonna define a score

example, for citation evaluator

```txt
Step 1
Identify all factual claims.

Step 2
Determine which require citations.

Step 3
Locate nearby citations.

Step 4
Evaluate source authority.

Step 5
Assign a score using the rubric.
scoring schema
"""
Score 5

• Nearly every factual claim has an authoritative citation.
• Sources are government, peer-reviewed, standards bodies, or official documentation.
• Citations directly support the adjacent claim.

Score 4

• Most factual claims cited.
• Small number of unsupported claims.

Score 3

• Some citations.
• Significant unsupported factual statements.

Score 2

• Few citations.

Score 1

• Rare citations.

Score 0

• No citations.
"""

Return JSON only.
```

algorithm

## evaluator score

```
E_i = (S_i / 5) * R_i
```

---

## trust & authority score

```
trust = ((e_citation + e_evidence) / 10) * 40
```

---

## content quality score

```
content = ((e_readability + e_entity + e_freshness + e_faq) / 15) * 35
```

---

## technical discoverability score

```
technical = ((e_schema + e_technical) / 7) * 25
```

---

## final geo score

```
geo = trust + content + technical
```

---

## evaluator confidence

```
ec_i = c_i * r_i
```

---

## trust confidence

```
trust_conf = ((ec_citation + ec_evidence) / 10)
```

---

## content confidence

```
content_conf = ((ec_readability + ec_entity + ec_freshness + ec_faq) / 15)
```

---

## technical confidence

```
technical_conf = ((ec_schema + ec_technical) / 7)
```

---

## Overall evaluation confidence

```
overall_confidence = 0.40 * trust_conf + 0.35 * content_conf + 0.25 * technical_conf
```

---

the numbers 10, 15 and 7 come the relevance of each geo technique(out of 5)

- citations to authoritative sources(5) (geo paper)
- supported quantitative stats(5): if not supported(3.5 to 3) (geo paper)
- quotations(again authoritative ones 5, non are useless) (geo paper)
- readability(4) (geo paper)
- entity richness(4): instead of company, say phazeai (google search central)
- schema.org(json-ld)(4) (google search central, since built over seo)
- freshness(4) (google search central, better for rag)
- faq(3) ~ since already under the information, the llm does not care if format is qa or some other way (source)
- internal linking(crawlability 3) (google search central, because geo is built over seo, so still relevant)
- meta tags(3) (google search central, because geo is built over seo, so still relevant)
- robots.txt and sitemap(3) ~ since crawling stars here, but this is not for seo but geo, does crawling even matter here, when the data is already crawled (google search central, because geo is built over seo, so still relevant since crawlability is important)
- llms.txt(2) (google search central) (why so less here: source)

then they are categorized adn each category has its own importance
- trust and authority(40%)
- content quality(35%)
- technical discoverability(25%)

---

output of each evaluator

```json
{
    "score": 4.5,                     // 0-5
    "confidence": 9.2,                // 0-10
    "summary": "Most factual claims are backed by authoritative sources, but several quantitative claims lack citations.",
    "findings": [
        {
            "title": "Unsupported quantitative claims",
            "severity": "high",
            "description": "Several benchmark claims are presented without authoritative citations.",
            "evidence": [
                {
                    "type": "claim",
                    "content": "GPT-4 improves performance by 40%."
                }
            ],
            "recommendation": "Cite peer-reviewed papers or official benchmark reports for every quantitative claim."
        },
        {
            "title": "Strong use of official documentation",
            "severity": "low",
            "description": "Most technical explanations reference OpenAI and Google documentation.",
            "evidence": [
                {
                    "type": "source",
                    "value": "OpenAI GPT-4 Technical Report"
                },
                {
                    "type": "source",
                    "value": "Google Search Central"
                }
            ],
            "recommendation": null
        }
    ],

    "metadata": {
        "evaluator": "Citation Authority Evaluator",
        "model": "gpt-5.5",
    }
}
```


the entire evaluation framework can be built using just three generic data models


```python
class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceType(Enum):
    CITATION = "citation"
    SOURCE = "source"
    CLAIM = "claim"
    STATISTIC = "statistic"
    ENTITY = "entity"
    DATE = "date"
    META_TAG = "meta_tag"
    SCHEMA = "schema"
    ROBOTS_RULE = "robots_rule"
    SITEMAP_ENTRY = "sitemap_entry"
    LLMS_TXT = "llms_txt"
    HEADING = "heading"
    CONTENT_SAMPLE = "content_sample"
    INTERNAL_LINK = "internal_link"
    EXTERNAL_LINK = "external_link"


@dataclass
class Evidence:
    """
    Atomic piece of evidence supporting a finding.
    """
    type: EvidenceType
    value: str
    explanation: str


@dataclass
class Finding:
    """
    A single observation made by an evaluator.
    """
    title: str
    severity: Severity

    description: str

    evidence: List[Evidence] = field(default_factory=list)

    recommendation: Optional[str] = None


@dataclass
class EvaluatorMetadata:
    """
    Metadata about the evaluation itself.
    """
    evaluator: str
    model: str

    evaluation_timestamp: Optional[str] = None
    execution_time_ms: Optional[int] = None

    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluatorOutput:
    """
    Standardized output for every GEO evaluator.
    """
    score: float                     # 0 - 5
    confidence: float                # 0 - 10

    summary: str

    findings: List[Finding] = field(default_factory=list)

    metadata: EvaluatorMetadata = field(default_factory=EvaluatorMetadata)
```