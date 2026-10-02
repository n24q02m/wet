---
name: fact-check
description: Verify a claim using adversarial search — find both supporting AND contradicting evidence
argument-hint: "[claim to verify]"
---

# Fact Check

Verify a claim by actively searching for BOTH supporting and contradicting evidence. Counteracts LLM confirmation bias by enforcing adversarial search.

## Steps

1. **Decompose the claim** into verifiable sub-claims:
   - Separate factual assertions from opinions
   - Identify the core falsifiable statement
   - Note the domain: scientific, technical, historical, statistical, or current events

2. **Search for SUPPORTING evidence** using `search`:
   - `search(action="search", query="[claim as stated]")`
   - For scientific claims: `search(action="search", query="[claim] research evidence", search_type="academic")`
   - Extract 2-3 strongest supporting sources with `extract`

3. **Search for CONTRADICTING evidence** (mandatory — do NOT skip):
   - `search(action="search", query="[claim] debunked OR wrong OR myth OR criticism")`
   - `search(action="search", query="[opposite of claim] evidence")`
   - For scientific claims: `search(action="search", query="[claim] replication failure OR meta-analysis", search_type="academic")`
   - Extract 2-3 strongest contradicting sources with `extract`

4. **Assess source quality** for each piece of evidence:
   - **Tier 1**: Peer-reviewed journals, official statistics, primary sources
   - **Tier 2**: Established news outlets, institutional reports, expert analysis
   - **Tier 3**: Blogs, forums, social media, opinion pieces
   - **Tier 4**: Anonymous sources, undated content, known biased outlets
   - Discard Tier 4 unless no better sources exist

5. **Produce verdict** with structured output:
   - **Claim**: [exact claim being checked]
   - **Verdict**: Supported / Partially Supported / Disputed / Unsupported / Insufficient Evidence
   - **Confidence**: High / Medium / Low (based on source tier and agreement)
   - **Supporting evidence**: [bullet list with source tier tags]
   - **Contradicting evidence**: [bullet list with source tier tags]
   - **Nuance**: [important caveats, context-dependence, or scope limitations]

## Decision Tree: Choosing Verdict

- All Tier 1-2 sources agree -> **Supported** (High confidence)
- Tier 1-2 support, some Tier 2-3 contradict -> **Partially Supported** (Medium)
- Tier 1-2 sources disagree with each other -> **Disputed** (note the split)
- Only Tier 3-4 sources support, Tier 1-2 contradict -> **Unsupported** (High)
- Fewer than 2 sources found either way -> **Insufficient Evidence** (Low)

## Common Pitfalls

- **Confirmation bias**: Searching only for supporting evidence. The contradicting search in step 3 is MANDATORY.
- **Recency bias**: Old but well-cited research may outweigh recent blog posts.
- **Authority bias**: A claim from a famous person still needs evidence.
- **Survivorship bias**: "X worked for company Y" does not mean X works in general.
- **Outdated facts**: Check publication dates. A 2020 statistic may be wrong in 2026.

## When to Use

- Verifying claims before including them in code comments or documentation
- Checking technical claims ("X is faster than Y", "Z is deprecated")
- Validating statistics or numerical claims from any source
- Fact-checking user assumptions before building on them
