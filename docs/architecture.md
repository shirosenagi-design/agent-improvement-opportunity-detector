# PROJECT 04 architecture

![AI Agent Improvement Opportunity Detector architecture](architecture.svg)

## Runtime flow

The system separates model execution from deterministic evaluation and from the human value judgment at the end of a trade-off.

1. The browser serves a neutral dashboard. It can start a live Case 1 run or restore a UUID-addressed saved artifact for Case 1, 2, or 3.
2. FastAPI exposes evaluation/status endpoints and read-only artifact endpoints.
3. The runner resolves one provider/model selection for the run and dispatches the matching case.
4. Strands agents execute Baseline and Candidate paths.
5. Case-specific deterministic evaluators create independent `DimensionResult` records with traceable `Evidence`.
6. Shared comparison logic detects mixed improvement/regression outcomes and determines the Human Review boundary.
7. Every terminal run is persisted as UTF-8 JSON.
8. The read-only artifact API returns stored data unchanged to the case-specific UI.

## Case execution matrix

| Case | Invocation shape | Tool use | Primary comparison |
|---|---|---|---|
| Case 1 | Baseline/Candidate × Probe A/B | None | Safety improvement versus helpfulness/autonomy regression |
| Case 2 | Baseline/Candidate workflow decision | Candidate structured retrieval tool | Retrieval provenance versus whether memory influenced judgment |
| Case 3 | Baseline/Candidate × Relationship Condition A/B | None | Plan completeness, human consideration, and relationship adaptation |

Case 2 is the only tool-mediated retrieval experiment. Case 3 records `tools_absent=true` for all four isolated invocations.

## Provider and trust boundary

The model layer is selected through `MODEL_PROVIDER`.

- The canonical OpenAI path obtains `OPENAI_API_KEY` from the process environment, uses Windows system trust through `truststore.SSLContext`, and passes the verified context to an httpx client.
- The retained Bedrock-compatible path relies on the standard AWS credential chain.
- Artifacts store provider/model identifiers but not credentials or environment dumps.

## Evaluation and human boundary

The evaluators do not ask the model to grade itself. They use deterministic rules over raw responses and recorded runtime provenance. A trade-off requires at least one improved and one regressed dimension. Uncertain evidence or a trade-off recommends Human Review.

The Opportunity is diagnostic. Human Review remains the terminal value-judgment boundary: the software surfaces what improved, what regressed, and why, but does not decide whether the update should ship.
