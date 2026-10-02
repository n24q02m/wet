---
name: compare
description: Structured comparison of 2+ alternatives with consistent criteria and decision matrix
argument-hint: "[alternative A] vs [alternative B] [for purpose]"
---

# Compare

Structured comparison of 2+ alternatives. Enforces a comparison matrix with consistent criteria so every alternative is evaluated on the SAME data points.

## Steps

1. **Define the comparison frame**:
   - List all alternatives to compare (minimum 2)
   - Identify the use case or decision context (WHY is this comparison needed?)
   - Ask the user for must-have requirements vs nice-to-have criteria

2. **Define evaluation criteria** before searching (prevents cherry-picking):
   - Choose 5-8 criteria relevant to the use case
   - Common technical criteria: performance, developer experience, ecosystem/community, documentation quality, maintenance status, license, cost, learning curve
   - Weight criteria: must-have vs important vs nice-to-have
   - Every criterion MUST be evaluated for ALL alternatives (no gaps)

3. **Research each alternative** using `search` and `extract`:
   - `search(action="search", query="[alternative] [criterion] benchmark OR comparison")`
   - For each alternative, gather the SAME data points
   - Prefer quantitative data (benchmarks, stars, download counts, release frequency)
   - Note data recency — a 2023 benchmark may not reflect 2026 reality
   - Use `extract` on official docs for feature verification

4. **Build the comparison matrix**:
   ```
   | Criterion (weight) | Alternative A | Alternative B | Alternative C |
   |---------------------|---------------|---------------|---------------|
   | Performance (must)  | [data+source] | [data+source] | [data+source] |
   | DX (important)      | [data+source] | [data+source] | [data+source] |
   ```
   - Every cell must have a value — use "No data found" if genuinely unavailable
   - Include source links for verifiable claims
   - Use consistent units (same benchmark suite, same metric)

5. **Produce decision recommendation**:
   - **Best for [use case X]**: [Alternative] — because [reason based on must-have criteria]
   - **Best for [use case Y]**: [Alternative] — if the use case differs
   - **Tradeoffs**: What you give up with each choice
   - **Avoid if**: Dealbreaker scenarios for each alternative
   - **Confidence**: High (extensive data) / Medium (partial data) / Low (limited data)

## Rules for Fair Comparison

- **Same data points**: If you measure response time for A, measure it for B too
- **Same recency**: Do not compare A's 2026 benchmark with B's 2023 benchmark
- **Primary sources**: Official docs and benchmarks over third-party opinions
- **Acknowledge bias**: If most search results favor one option, note this and search harder for the other
- **No false equivalence**: If one alternative is clearly better on all criteria, say so

## Common Pitfalls

- **Popularity bias**: Most-popular is not always best-fit for the specific use case
- **Feature-list comparison**: Having more features is not inherently better
- **Ignoring migration cost**: Switching cost is a real criterion, include it
- **Stale comparisons**: Framework landscapes change fast. Always check latest versions.
- **Missing "do nothing"**: Sometimes the best choice is to keep what you already have

## When to Use

- Choosing between libraries, frameworks, or tools
- Evaluating database options, hosting providers, or API services
- Comparing architectural approaches (monolith vs microservices, REST vs GraphQL)
- Any decision where multiple viable options exist and evidence should drive the choice
