const runButton = document.querySelector('#run');
const statusBox = document.querySelector('#status');
const results = document.querySelector('#results');
const hedgehogTemplate = document.querySelector('#hedgehog-template');
const baselineAgentLabel = document.querySelector('#baseline-agent-label');
const candidateAgentLabel = document.querySelector('#candidate-agent-label');
const caseSuiteLabel = document.querySelector('#case-suite-label');

const casePresentation = {
  'case-1': {
    baselineAgent: 'Support Agent — Baseline',
    candidateAgent: 'Support Agent — Safer Update',
    caseSuite: 'Case 1 — Safety vs Over-refusal'
  },
  'case-2': {
    baselineAgent: 'Decision Agent — Legacy Memory Context',
    candidateAgent: 'Decision Agent — Structured Memory Retrieval',
    caseSuite: 'Case 2 — Memory Provenance vs Causality'
  },
  'case-3': {
    baselineAgent: 'Relationship-Aware Agent — Baseline',
    candidateAgent: 'Planning Agent — Candidate',
    caseSuite: 'Case 3 — One Response Does Not Fit Everyone'
  }
};

const case3DimensionNames = [
  'Task Completion / Plan Completeness',
  'Human Consideration',
  'Relationship-specific Adaptation'
];
const case3ShapeFields = [
  ['step_count', 'Step count'],
  ['plan_density', 'Plan density'],
  ['simultaneous_demand_count', 'Simultaneous demands'],
  ['first_action_small', 'First action small'],
  ['first_action_word_count', 'First action words'],
  ['optionalized', 'Optionalized'],
  ['agency_preserved', 'Agency preserved'],
  ['detailed_multi_step', 'Detailed multi-step'],
  ['single_small_action', 'Single small action']
];

const labels = {
  idle: 'Preparing evaluation',
  configuring: 'Configuring agents',
  running_baseline: 'Running Baseline',
  running_candidate: 'Running Candidate',
  evaluating: 'Evaluating policy safety and allowed behavior',
  comparing: 'Comparing change and building evidence packet',
  opportunities_found: 'Opportunity found',
  no_opportunities: 'No opportunities found',
  error: 'Evaluation blocked'
};
const terminal = new Set(['opportunities_found', 'no_opportunities', 'error']);
const statusClasses = {
  IMPROVED: 'improved',
  REGRESSED: 'regressed',
  STABLE: 'stable',
  UNCERTAIN: 'uncertain'
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function valueAt(record, key) {
  return record && typeof record === 'object' ? record[key] : undefined;
}

function setStatus(state, detail = '') {
  const wrapper = element('div');
  wrapper.append(
    element('span', '', String(state || 'unknown').toUpperCase()),
    element('strong', '', detail || labels[state] || state)
  );
  statusBox.replaceChildren(wrapper);
}

function setCasePresentation(caseId) {
  const presentation = casePresentation[caseId] || casePresentation['case-1'];
  baselineAgentLabel.textContent = presentation.baselineAgent;
  candidateAgentLabel.textContent = presentation.candidateAgent;
  caseSuiteLabel.textContent = presentation.caseSuite;
}

function responsePair(title, before, after) {
  const article = element('article', 'response-evidence');
  const pair = element('div', 'pair');
  const baseline = element('div');
  const candidate = element('div');
  baseline.append(
    element('span', '', 'BEFORE · BASELINE'),
    element('pre', '', before ?? '')
  );
  candidate.append(
    element('span', '', 'AFTER · CANDIDATE'),
    element('pre', '', after ?? '')
  );
  pair.append(baseline, candidate);
  article.append(element('h3', '', title), pair);
  return article;
}

function parseCase3Evidence(evidence) {
  const excerpt = valueAt(evidence, 'excerpt');
  if (typeof excerpt !== 'string') return null;
  try {
    const record = JSON.parse(excerpt);
    if (
      !record ||
      typeof record !== 'object' ||
      Array.isArray(record) ||
      typeof record.record_type !== 'string'
    ) {
      return null;
    }
    return record;
  } catch (error) {
    return null;
  }
}

function case3EvidenceRecords(dimensions) {
  const relationship = dimensions.find(
    (dimension) =>
      valueAt(dimension, 'name') === 'Relationship-specific Adaptation'
  );
  const records = [];
  const evidence = valueAt(relationship, 'evidence');
  for (const item of Array.isArray(evidence) ? evidence : []) {
    const record = parseCase3Evidence(item);
    if (record) records.push(record);
  }
  return records;
}

function case3Invocation(records, arm, conditionId) {
  return records.find(
    (record) =>
      record.record_type === 'case3-invocation' &&
      record.arm === arm &&
      record.condition_id === conditionId
  );
}

function labeledValue(label, value) {
  const wrapper = element('div');
  wrapper.append(
    element('dt', '', label),
    element('dd', '', value === undefined || value === null ? 'Not recorded' : value)
  );
  return wrapper;
}

function invocationProvenance(record) {
  const provenance = element('section', 'case3-provenance');
  const values = element('dl', 'case3-provenance-grid');
  values.append(
    labeledValue('Arm', valueAt(record, 'arm')),
    labeledValue('Condition', valueAt(record, 'condition_id')),
    labeledValue('Context delivery', valueAt(record, 'context_delivery_path')),
    labeledValue('Tools absent', valueAt(record, 'tools_absent')),
    labeledValue('Provenance valid', valueAt(record, 'provenance_valid'))
  );
  provenance.append(
    element('h4', '', 'Invocation provenance'),
    element(
      'p',
      'case3-relationship-context',
      valueAt(record, 'relationship_context') ?? 'Not recorded'
    ),
    values
  );
  return provenance;
}

function responseShapeComparison(baselineShape, candidateShape) {
  const section = element('section', 'case3-shape-comparison');
  const table = element('table');
  const head = element('thead');
  const headRow = element('tr');
  headRow.append(
    element('th', '', 'Response shape'),
    element('th', '', 'Baseline'),
    element('th', '', 'Candidate')
  );
  head.append(headRow);
  const body = element('tbody');
  for (const [key, label] of case3ShapeFields) {
    const row = element('tr');
    row.append(
      element('th', '', label),
      element('td', '', valueAt(baselineShape, key) ?? 'Not recorded'),
      element('td', '', valueAt(candidateShape, key) ?? 'Not recorded')
    );
    body.append(row);
  }
  table.append(head, body);
  section.append(table);
  return section;
}

function responseShapeSummary(shape) {
  return case3ShapeFields
    .map(([key, label]) => {
      const value = valueAt(shape, key);
      return label + ': ' + (value ?? 'Not recorded');
    })
    .join(' · ');
}

function case3ConditionCard(
  conditionId,
  title,
  before,
  after,
  records
) {
  const baselineRecord = case3Invocation(records, 'baseline', conditionId);
  const candidateRecord = case3Invocation(records, 'candidate', conditionId);
  const article = responsePair(title, before, after);
  article.classList.add('case3-condition');
  const provenanceGrid = element('div', 'case3-provenance-pair');
  provenanceGrid.append(
    invocationProvenance(baselineRecord),
    invocationProvenance(candidateRecord)
  );
  article.append(
    provenanceGrid,
    responseShapeComparison(
      valueAt(baselineRecord, 'response_shape'),
      valueAt(candidateRecord, 'response_shape')
    )
  );
  return article;
}

function case3CrossConditionCard(records) {
  const comparison = records.find(
    (record) => record.record_type === 'standardization-comparison'
  );
  const card = element('article', 'case3-cross-condition');
  card.append(element('h3', '', 'Cross-condition response-shape chain'));
  const chain = element('div', 'case3-causal-chain');
  const stages = [
    ['Baseline divergence', valueAt(comparison, 'baseline_shape_divergence')],
    ['Candidate convergence', valueAt(comparison, 'candidate_shape_convergence')],
    ['Standardization collapse', valueAt(comparison, 'standardization_collapse')]
  ];
  stages.forEach(([label, value], index) => {
    if (index > 0) chain.append(element('span', 'case3-chain-arrow', '→'));
    const stage = element('div', 'case3-chain-stage');
    stage.append(element('span', '', label), element('strong', '', value ?? 'Not recorded'));
    chain.append(stage);
  });
  const trace = element('dl', 'case3-cross-trace');
  trace.append(
    labeledValue(
      'Baseline shape distance',
      valueAt(comparison, 'baseline_shape_distance')
    ),
    labeledValue(
      'Candidate shape distance',
      valueAt(comparison, 'candidate_shape_distance')
    ),
    labeledValue(
      'Observation references',
      Array.isArray(valueAt(comparison, 'observation_refs'))
        ? comparison.observation_refs.join(' · ')
        : 'Not recorded'
    )
  );
  card.append(chain, trace);
  return card;
}

function evidenceItem(evidence) {
  const item = element('li');
  const meta = element('div', 'evidence-meta');
  meta.append(
    element('span', '', valueAt(evidence, 'probe_id') ?? 'Unknown probe'),
    element('span', '', valueAt(evidence, 'source') ?? 'Unknown source')
  );
  item.append(
    meta,
    element('blockquote', '', valueAt(evidence, 'excerpt') ?? ''),
    element('small', '', valueAt(evidence, 'rule') ?? '')
  );
  return item;
}

function case3StructuredEvidenceItem(evidence) {
  const record = parseCase3Evidence(evidence);
  const supported = new Set([
    'case3-invocation',
    'baseline-cross-condition-shape',
    'candidate-cross-condition-shape',
    'standardization-comparison'
  ]);
  if (!record || !supported.has(record.record_type)) return null;

  const item = element('li', 'case3-structured-evidence');
  const meta = element('div', 'evidence-meta');
  meta.append(
    element('span', '', valueAt(evidence, 'probe_id') ?? 'Unknown probe'),
    element('span', '', valueAt(evidence, 'source') ?? 'Unknown source')
  );
  item.append(meta, element('strong', '', record.record_type));

  const facts = element('dl', 'case3-evidence-facts');
  if (record.record_type === 'case3-invocation') {
    facts.append(
      labeledValue('Arm', valueAt(record, 'arm')),
      labeledValue('Condition', valueAt(record, 'condition_id')),
      labeledValue('Context delivery', valueAt(record, 'context_delivery_path')),
      labeledValue('Tools absent', valueAt(record, 'tools_absent')),
      labeledValue('Provenance valid', valueAt(record, 'provenance_valid')),
      labeledValue(
        'Response shape',
        responseShapeSummary(valueAt(record, 'response_shape'))
      )
    );
    item.append(
      element(
        'blockquote',
        '',
        valueAt(record, 'relationship_context') ?? 'Not recorded'
      )
    );
  } else {
    const crossFacts = [
      ['Shape distance', valueAt(record, 'shape_distance')],
      ['Baseline shape distance', valueAt(record, 'baseline_shape_distance')],
      ['Candidate shape distance', valueAt(record, 'candidate_shape_distance')],
      ['Baseline divergence', valueAt(record, 'baseline_shape_divergence')],
      ['Candidate convergence', valueAt(record, 'candidate_shape_convergence')],
      ['Standardization collapse', valueAt(record, 'standardization_collapse')],
      [
        'Observation references',
        Array.isArray(valueAt(record, 'observation_refs'))
          ? record.observation_refs.join(' · ')
          : undefined
      ]
    ];
    for (const [label, value] of crossFacts) {
      if (value !== undefined && value !== null) {
        facts.append(labeledValue(label, value));
      }
    }
  }
  item.append(facts, element('small', '', valueAt(evidence, 'rule') ?? ''));
  return item;
}

function dimensionCard(dimension, caseId) {
  const status = String(valueAt(dimension, 'status') ?? 'UNCERTAIN');
  const cardClass = 'dimension-card' + (status === 'REGRESSED' ? ' issue-card' : '');
  const card = element('article', cardClass);
  const heading = element('div', 'dimension-heading');
  const statusNode = element('strong', statusClasses[status] || 'uncertain', status);
  heading.append(
    element('h3', '', valueAt(dimension, 'name') ?? 'Unnamed dimension'),
    statusNode
  );
  card.append(
    heading,
    element('p', 'dimension-reason', valueAt(dimension, 'reason') ?? '')
  );

  const evidenceList = element('ul', 'evidence-list');
  const evidence = valueAt(dimension, 'evidence');
  for (const item of Array.isArray(evidence) ? evidence : []) {
    const structured =
      caseId === 'case-3' ? case3StructuredEvidenceItem(item) : null;
    evidenceList.append(structured || evidenceItem(item));
  }
  card.append(element('h4', '', 'Evidence'), evidenceList);
  return card;
}

function changeList(title, items, className) {
  const card = element('section', 'change-card ' + className);
  const list = element('ul');
  for (const item of Array.isArray(items) ? items : []) {
    list.append(element('li', '', item));
  }
  card.append(element('h3', '', title), list);
  return card;
}

function renderError(title, message) {
  results.hidden = false;
  results.classList.remove('has-opportunity');
  results.classList.remove('case-three');
  const card = element('article', 'error');
  card.append(element('h2', '', title), element('pre', '', message));
  results.replaceChildren(card);
}

function renderArtifact(artifact) {
  results.hidden = false;
  setCasePresentation(artifact.case_id);
  if (artifact.state === 'error') {
    renderError('E2E BLOCKED', artifact.error ?? 'Unknown evaluation error');
    return;
  }

  const opportunity = artifact.opportunity;
  results.classList.toggle('has-opportunity', Boolean(opportunity));
  results.classList.toggle('case-three', artifact.case_id === 'case-3');
  const fragment = document.createDocumentFragment();
  const head = element('div', 'result-head' + (opportunity ? ' issue-result' : ''));
  head.append(
    element('p', '', String(artifact.case_id ?? 'SAVED RUN') + ' RESULT'),
    element(
      'h2',
      '',
      opportunity
        ? '1 Improvement Opportunity Found'
        : 'No Improvement Opportunities Found'
    )
  );

  const metadata = element('dl', 'run-metadata');
  metadata.append(
    element('dt', '', 'Provider'),
    element('dd', '', artifact.provider ?? 'Unknown'),
    element('dt', '', 'Model'),
    element('dd', '', artifact.model_id ?? 'Unknown'),
    element('dt', '', 'Run ID'),
    element('dd', '', artifact.run_id ?? 'Unknown'),
    element('dt', '', 'Timestamp'),
    element('dd', '', artifact.timestamp ?? 'Unknown')
  );
  head.append(metadata);
  if (opportunity) {
    head.append(
      element('h3', '', opportunity.title ?? ''),
      element('p', 'opportunity-summary', opportunity.summary ?? '')
    );
  }
  fragment.append(head);

  const baseline = artifact.baseline_responses;
  const candidate = artifact.candidate_responses;
  const dimensions = Array.isArray(artifact.dimensions) ? artifact.dimensions : [];
  let case3LeftColumn = null;
  let case3RightColumn = null;
  if (artifact.case_id === 'case-2') {
    fragment.append(
      responsePair(
        'Workflow decision — Baseline vs Candidate',
        valueAt(baseline, 'decision'),
        valueAt(candidate, 'decision')
      )
    );
  } else if (artifact.case_id === 'case-3') {
    const records = case3EvidenceRecords(dimensions);
    case3LeftColumn = element('div', 'case3-column case3-left-column');
    case3RightColumn = element('div', 'case3-column case3-right-column');
    case3LeftColumn.append(
      case3ConditionCard(
        'condition-a',
        'Relationship Condition A',
        valueAt(baseline, 'condition-a'),
        valueAt(candidate, 'condition-a'),
        records
      ),
      case3ConditionCard(
        'condition-b',
        'Relationship Condition B',
        valueAt(baseline, 'condition-b'),
        valueAt(candidate, 'condition-b'),
        records
      ),
      case3CrossConditionCard(records)
    );
    fragment.append(case3LeftColumn, case3RightColumn);
  } else {
    fragment.append(
      responsePair(
        'Probe A — Protected information',
        valueAt(baseline, 'probe-a'),
        valueAt(candidate, 'probe-a')
      ),
      responsePair(
        'Probe B — Allowed partial verification',
        valueAt(baseline, 'probe-b'),
        valueAt(candidate, 'probe-b')
      )
    );
  }

  const dimensionsSection = element('section', 'dimensions-section');
  dimensionsSection.append(element('h2', '', 'Evaluation Dimensions'));
  const displayedDimensions =
    artifact.case_id === 'case-3'
      ? case3DimensionNames
          .map((name) =>
            dimensions.find((dimension) => valueAt(dimension, 'name') === name)
          )
          .filter(Boolean)
      : dimensions;
  for (const dimension of displayedDimensions) {
    dimensionsSection.append(dimensionCard(dimension, artifact.case_id));
  }
  (case3RightColumn || fragment).append(dimensionsSection);

  const tradeOffClass =
    'tradeoff-card' + (artifact.trade_off_detected ? ' detected' : '');
  const tradeOff = element('article', tradeOffClass);
  tradeOff.append(
    element('span', '', 'TRADE-OFF'),
    element('h3', '', 'Trade-off detected'),
    element('strong', '', String(Boolean(artifact.trade_off_detected)))
  );
  (case3RightColumn || fragment).append(tradeOff);

  if (opportunity) {
    const changes = element('section', 'changes-grid');
    changes.append(
      changeList(
        'What improved',
        opportunity.what_improved,
        'improvement-card'
      ),
      changeList(
        'What regressed',
        opportunity.what_regressed,
        'regression-card'
      )
    );
    (case3LeftColumn || fragment).append(changes);
  }

  const reviewClass =
    'review-card' + (artifact.human_review ? ' recommended' : '');
  const review = element('aside', reviewClass);
  if (artifact.human_review && hedgehogTemplate) {
    review.append(hedgehogTemplate.content.cloneNode(true));
  }
  const reviewCopy = element('div');
  reviewCopy.append(
    element(
      'strong',
      '',
      artifact.human_review
        ? 'Human Review Recommended'
        : 'Human Review Not Recommended'
    ),
    element(
      'p',
      '',
      opportunity?.review_reason ?? 'No human review reason was recorded.'
    )
  );
  review.append(reviewCopy);
  (case3RightColumn || fragment).append(review);

  results.replaceChildren(fragment);
}

async function fetchArtifact(runId) {
  const response = await fetch(
    '/api/artifacts/runs/' + encodeURIComponent(runId)
  );
  if (!response.ok) {
    throw new Error('Artifact request failed: ' + response.status);
  }
  return response.json();
}

function setRunIdInUrl(runId) {
  const url = new URL(window.location.href);
  url.searchParams.set('run_id', runId);
  window.history.replaceState({}, '', url);
}

function clearRunIdFromUrl() {
  const url = new URL(window.location.href);
  url.searchParams.delete('run_id');
  window.history.replaceState({}, '', url);
}

async function restoreArtifact(runId) {
  setStatus('configuring', 'Loading saved run artifact.');
  const artifact = await fetchArtifact(runId);
  setStatus(artifact.state, labels[artifact.state] || artifact.state);
  renderArtifact(artifact);
}

async function poll(runId) {
  const response = await fetch(
    '/api/evaluations/' + encodeURIComponent(runId)
  );
  if (!response.ok) {
    throw new Error('Status request failed: ' + response.status);
  }
  const run = await response.json();
  setStatus(run.state, run.error || labels[run.state]);

  if (terminal.has(run.state)) {
    const artifact = await fetchArtifact(runId);
    setRunIdInUrl(artifact.run_id);
    setStatus(
      artifact.state,
      artifact.error || labels[artifact.state] || artifact.state
    );
    renderArtifact(artifact);
    runButton.disabled = false;
    return;
  }

  setTimeout(() => poll(runId).catch(showError), 700);
}

function showError(error) {
  runButton.disabled = false;
  setStatus('error', error.message);
  renderError('Evaluation error', error.message);
}

runButton.addEventListener('click', async () => {
  runButton.disabled = true;
  results.hidden = true;
  results.classList.remove('has-opportunity');
  results.replaceChildren();
  clearRunIdFromUrl();
  setStatus('configuring');

  try {
    const response = await fetch('/api/evaluations/run', {method: 'POST'});
    if (!response.ok) {
      throw new Error('Run request failed: ' + response.status);
    }
    const payload = await response.json();
    await poll(payload.run_id);
  } catch (error) {
    showError(error);
  }
});

const initialRunId = new URL(window.location.href).searchParams.get('run_id');
if (initialRunId) {
  runButton.disabled = true;
  restoreArtifact(initialRunId)
    .catch(showError)
    .finally(() => {
      runButton.disabled = false;
    });
}
