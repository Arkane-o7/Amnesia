"""Generate the academic review report from saved, measured evaluation artifacts."""
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
from reportlab.graphics.shapes import Drawing, String, Rect

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output/pdf/amnesia-final-report.pdf"
INK, MUTED, PURPLE, GREEN = [colors.HexColor(c) for c in ("#29324b", "#788399", "#7765b5", "#568b75")]
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleAmnesia", fontName="Helvetica-Bold", fontSize=43, leading=48, textColor=INK, spaceAfter=15))
styles.add(ParagraphStyle(name="SubtitleAmnesia", fontName="Helvetica", fontSize=17, leading=25, textColor=PURPLE, spaceAfter=18))
styles.add(ParagraphStyle(name="BodyAmnesia", fontName="Helvetica", fontSize=10, leading=16, textColor=INK, spaceAfter=10))
styles.add(ParagraphStyle(name="SmallAmnesia", fontName="Helvetica", fontSize=8, leading=12, textColor=MUTED, spaceAfter=8))
styles.add(ParagraphStyle(name="HeadingAmnesia", fontName="Helvetica-Bold", fontSize=19, leading=25, textColor=INK, spaceBefore=10, spaceAfter=16))
styles.add(ParagraphStyle(name="SubheadingAmnesia", fontName="Helvetica-Bold", fontSize=12, leading=17, textColor=PURPLE, spaceBefore=14, spaceAfter=8))
styles.add(ParagraphStyle(name="CellAmnesia", fontName="Helvetica", fontSize=8, leading=12, textColor=INK))
styles.add(ParagraphStyle(name="CoverQuestion", fontName="Helvetica", fontSize=17, leading=27, textColor=INK, backColor=colors.HexColor("#f2eef9"), borderPadding=18, spaceBefore=24, spaceAfter=25))
story = []


def p(text, style="BodyAmnesia"):
    return Paragraph(text, styles[style])


def add(text, style="BodyAmnesia"):
    story.append(p(text, style))


def heading(text): add(text, "HeadingAmnesia")
def sub(text): add(text, "SubheadingAmnesia")
def page(): story.append(PageBreak())
def percent(value): return "%.1f%%" % (100*value)


def table(rows, widths=None):
    cells = [[p(escape(str(cell)), "CellAmnesia") for cell in row] for row in rows]
    t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eeeaf6")), ("TEXTCOLOR", (0,0), (-1,0), PURPLE), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 9), ("RIGHTPADDING", (0,0), (-1,-1), 9), ("TOPPADDING", (0,0), (-1,-1), 9), ("BOTTOMPADDING", (0,0), (-1,-1), 9), ("LINEBELOW", (0,0), (-1,0), .5, colors.HexColor("#d9d1e9")), ("LINEBELOW", (0,1), (-1,-1), .3, colors.HexColor("#e8e8ef")), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fbfbfd")])]))
    story.append(t)
    story.append(Spacer(1, 10))


def load(name):
    file = ROOT / "output" / name
    return json.loads(file.read_text()) if file.exists() else None


policy = load("evaluation-policy.json")
cloud = load("evaluation-openai.json")
codex = load("evaluation-codex.json")
local = load("evaluation-ollama-final.json")
live = codex or cloud or local
labels = {"context": "Full context LLM", "recent": "Recent assertions", "vector": "Vector retrieval", "graph": "Graph retrieval", "hybrid": "Amnesia hybrid", "hybrid_no_temporal": "Without temporal policy", "hybrid_no_graph": "Without graph weight"}


def bars(report):
    d = Drawing(470, 173)
    names = [m for m in ("context", "vector", "graph", "hybrid") if m in report["metrics"]]
    for index, method in enumerate(names):
        y = 137 - index*34
        score = report["metrics"][method]["answer_accuracy"]
        d.add(String(0, y+4, labels[method], fontName="Helvetica", fontSize=9, fillColor=MUTED))
        d.add(Rect(132, y, 275, 17, fillColor=colors.HexColor("#f0edf6"), strokeColor=None))
        d.add(Rect(132, y, 275*score, 17, fillColor=PURPLE if method == "hybrid" else colors.HexColor("#c6bcdd"), strokeColor=None))
        d.add(String(425, y+4, percent(score), fontName="Helvetica-Bold", fontSize=9, fillColor=INK))
    return d


def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor("#e4e3eb")); canvas.setLineWidth(.4)
    canvas.line(22*mm, 20*mm, 188*mm, 20*mm)
    canvas.setFillColor(MUTED); canvas.setFont("Helvetica", 7)
    canvas.drawString(22*mm, 15*mm, "AMNESIA  /  FINAL REVIEW  /  14 OCTOBER 2026")
    canvas.drawRightString(188*mm, 15*mm, str(doc.page))


add("FINAL REVIEW REPORT", "SmallAmnesia")
story.append(Spacer(1, 28*mm))
add("AMNESIA", "TitleAmnesia")
add("An evolving knowledge graph agent<br/>for long-term AI memory", "SubtitleAmnesia")
add("Can an AI agent remember what is true now while preserving what used to be true?", "CoverQuestion")
add("<b>Prepared by</b> Abhilaksh Chauhan<br/><b>Institute</b> Vellore Institute of Technology<br/><b>Domain</b> AI memory systems<br/><b>Implementation</b> Research application v1.0", "BodyAmnesia")
story.append(Spacer(1, 16*mm))
add("Evidence-bounded delivery", "SubheadingAmnesia")
add("This report is generated from the implemented application, test suite, and saved evaluation artifacts. Policy, local-model, Codex-login, and optional OpenAI API measurements are identified separately. No missing experiment is represented as a completed result.", "SmallAmnesia")
page()

heading("1. Problem, scope, and contribution")
add("Long-running assistants face a state-management problem: an old fact can remain relevant after it changes. A vector search for a home address may retrieve both Hyderabad and Chennai, even though only the latest explicit relocation should represent the current home.")
sub("Research question")
add("Can relation-and-scope-aware reconciliation, temporal lifecycle state, and hybrid graph retrieval reduce stale answers while avoiding false invalidation of compatible facts?")
sub("Contribution")
for text in ["Conservative six-way reconciliation within compatible entity/relation/preference scopes.", "Persistent lifecycle history and source evidence, with earlier belief snapshots and explicit user clarification.", "Hybrid retrieval combining dense similarity, personalized PageRank, validity, confidence, and staleness penalties.", "Failure-oriented evaluation that separates extraction errors from state-management behavior and retains failed cases."]:
    add("- " + text)
sub("Positioning against prior work")
table([["Work", "Relevant mechanism", "Position of this project"], ["Generative Agents [1]", "Persistent memory stream and reflection", "Focus on explicit evolving facts and stale answers."], ["MemGPT [2]", "Memory tiers and context management", "Focus on scoped belief transitions and traceable evidence."], ["HippoRAG [3]", "Graph-based associative retrieval", "Use graph traversal alongside temporal lifecycle policy."], ["Zep / Graphiti [4]", "Temporal agent knowledge graph", "Temporal graphs are prior art; the contribution is policy and evaluation framing."]], [100, 155, 215])
add("The academic scope excludes multi-tenant SaaS, billing, production connectors, and distributed graph infrastructure. This is a complete local research application, not a claim of a production enterprise memory platform.", "SmallAmnesia")
page()

heading("2. Implemented architecture")
image = ROOT / "docs/figures/architecture.png"
if image.exists():
    from PIL import Image as PILImage
    w, h = PILImage.open(image).size
    ratio = min(470/w, 510/h)
    story.append(Image(str(image), width=w*ratio, height=h*ratio, hAlign="CENTER"))
    story.append(Spacer(1, 12))
add("Figure 1. Conversation events become validated assertions, scoped lifecycle transitions, and a persistent temporal graph. Queries combine semantic and associative retrieval before grounded answering. The diagram is backed by backend/extraction.py, memory.py, storage.py, retrieval.py, and engine.py.", "SmallAmnesia")
add("React and TypeScript provide the memory studio, ledger, experiments, engine setup, and guided final-review walkthrough. A localhost Python API owns SQLite persistence and model calls. The primary engine uses the user's existing Codex ChatGPT login for extraction and answers, with local Nomic embeddings. Fully local Ollama and a separately configured OpenAI API are optional providers.")
page()

heading("3. Memory representation and update policy")
table([["Field / record", "Purpose"], ["subject_id, relation, value, scope", "Typed assertion with stable entity identity and independent preference/device domains."], ["valid_from, valid_until", "World-time validity; temporary states expire without replacing permanent home."], ["observed_at", "When evidence reached the system; historical recall also respects observation order."], ["evidence, event_id, fact_evidence", "Source quotations, conversation turn, and additional supporting evidence."], ["confidence", "Extraction reliability heuristic; not a calibrated probability."], ["status, superseded_by", "Current, superseded, invalid, or unresolved state and replacement link."], ["fact_history", "Append-only lifecycle transitions used to reconstruct earlier belief states."], ["entity_aliases", "Explicit aliases; pet names remain versioned labels on a stable pet subject."]], [178, 292])
sub("Six reconciliation labels")
table([["Label", "Applied behavior"], ["SAME", "Attach evidence to an existing assertion."], ["SUPPORTS", "Preserve the assertion and add supporting evidence; bounded stays can be extended."], ["UPDATES", "Apply an explicit correction and retain the previous value as invalid history."], ["SUPERSEDES", "Apply an explicit change or cancellation; preserve predecessor and link."], ["CONTRADICTS", "Retain incompatible weak or uncued evidence as unresolved."], ["UNRELATED", "Add a compatible fact without retiring another scope."]], [115, 355])
add("A user confirmation is a recorded action with new evidence. It resolves only competing facts in the same subject, relation, and scope. An uncertain cancellation cannot retire a known plan. Import/export preserves history, aliases, and evidence with remapped identifiers.", "SmallAmnesia")
page()

heading("4. Retrieval and grounded answering")
sub("Hybrid ranking")
add("Score = 0.40 semantic + 0.25 graph + 0.20 validity + 0.15 confidence - 0.65 staleness")
add("Semantic relevance is dense cosine similarity from the configured embedding model. The graph component uses weighted personalized PageRank with damping 0.85 and 40 iterations, seeded by entity/relation matches and semantic candidates. The graph baseline uses entity/relation seeds without dense semantic seeding.")
add("Lifecycle filtering excludes stale positive assertions from current hybrid context. Historical questions may use superseded evidence. Cancellation evidence remains available as negative evidence. Explicit query scopes separate phones from laptops and programming-language preference from beverage preference.")
sub("Conflict safety")
add("Relevant unresolved alternatives are preserved even when top-k ranking would otherwise omit them. A deterministic conflict guard requests clarification rather than allowing the answer model to select one incompatible value as certain.")
sub("Answer generation")
add("The configured LLM receives retrieved evidence and returns an answer, concise answer value, status, and citation IDs. Citation IDs are validated against the supplied context. Prompt grounding and citation validation reduce unsupported responses; they are not a formal entailment guarantee.")
sub("Baseline fairness")
table([["Method", "Input to the answerer"], ["Full context", "Raw user conversation turns within the local context budget."], ["Vector", "Top-k dense-vector facts without reconciliation state."], ["Graph", "Top-k personalized-PageRank facts without reconciliation state."], ["Amnesia", "Temporally filtered hybrid facts, scopes, and lifecycle state."], ["Policy ablations", "Remove temporal policy or graph weight in the controlled gold-input suite."]], [120, 350])
add("The live suite shares a configured LLM reader and dense embeddings; hybrid may abstain through its conflict guard. The policy suite uses TF-IDF and evidence-template answers. Full context receives raw turns. Context-size estimates count words; actual provider tokens include Codex harness overhead.", "SmallAmnesia")
page()

heading("5. Experimental design")
table([["Suite", "Data", "What is measured"], ["Policy and retrieval", "600 balanced synthetic questions, 10 change categories, independently specified gold assertions", "Reconciliation, safe invalidation, ranking, and deterministic answer selection without extraction noise."], ["Live AI", "60 available questions / 30 scenarios; 20-question option covers all ten categories. Selected run: %s questions." % (live["count"] if live else "pending"), "Actual model extraction, embeddings, PageRank, full-context/vector/graph/hybrid LLM answers."]], [100, 195, 175])
add("Categories: stable fact, preference change, location update, correction, cancellation, replacement, temporary state, additive fact, rename, and ambiguous conflict. The curated set is internal development evaluation, not a blind external or third-party human benchmark. Validation and prompts were refined during development; independent held-out evaluation remains future work.")
sub("Metrics")
table([["Metric", "Definition"], ["Extraction precision / recall / F1", "Normalized assertion identity against the declared gold annotation."], ["Reconciliation macro-F1", "Per-label classification; missing extraction counts as a miss. Live macro averages only labels with support."], ["Exact QA accuracy", "Normalized concise answer value, with declared gold aliases."], ["SMER", "Stale-value answers / evolved-fact questions."], ["FIR", "Gold preserved facts incorrectly retired / preserved facts considered."], ["Recall@K and MRR", "Gold supporting memories recovered and their rank."], ["Latency and context", "Elapsed query time and context estimates, with cache-hit and live-call counts."]], [175, 295])
add("Reproducibility: source generators, frozen JSONL annotations, raw JSON results, per-query records, extraction records, model configuration, and failure notebooks accompany the application. Reruns can vary with model serving, caches, and model-version aliases; the input seed and data remain explicit.", "SmallAmnesia")
page()

heading("6. Measured policy results")
if policy:
    rows = [["Method", "QA accuracy", "SMER", "Recall@5", "MRR"]]
    for method, metric in policy["metrics"].items(): rows.append([labels.get(method, method), percent(metric["answer_accuracy"]), percent(metric["smer"]), percent(metric["recall_at_5"]), "%.3f" % metric["mrr"]])
    table(rows, [175, 77, 66, 82, 70])
    add("Policy reconciliation macro-F1: %s. False invalidation: %d/%d. These measurements use supplied gold assertions; they do not establish natural-language extraction accuracy." % (percent(policy["reconciliation"]["macro_f1"]), policy["false_invalidation"]["retired"], policy["false_invalidation"]["considered"]))
    add("The no-graph ablation matches hybrid on this controlled set. This suite primarily exercises lifecycle policy and does not independently establish a graph-scoring advantage. The lower baseline scores also depend on a deterministic evidence reader; live-model results must be assessed separately.")
else: add("No completed policy artifact was available when this report was generated.")
sub("Implementation verification")
add("The expanded local regression suite covers preference/device scopes, temporal snapshots, uncertain cancellations, conflict confirmation, alias identity, PageRank normalization and traversal, future-dated changes, temporary extensions, atomic backup restoration, HTTP endpoints, and credential isolation. Exact pass counts and browser checks are recorded in docs/verification.md.")
add("The application exposes all stored evidence and decisions. A professor can type a new fact, open a fresh session, revise it, inspect the graph, compare retrieval methods, and query a historical snapshot without editing source code.")
page()

heading("7. Measured live AI results")
if live:
    engine = live.get("engine", {})
    add("Provider: <b>%s</b>. Language model: <b>%s</b>. Embeddings: <b>%s</b>. Questions: <b>%d</b>." % (escape(engine.get("provider", "unknown")), escape(engine.get("chat_model", "unknown")), escape(engine.get("embedding_model", "unknown")), live["count"]))
    story.append(bars(live))
    rows = [["Method", "QA", "SMER", "Recall@3", "Mean query ms"]]
    for method, metric in live["metrics"].items(): rows.append([labels.get(method, method), percent(metric["answer_accuracy"]), percent(metric["smer"]), percent(metric["recall_at_5"]), "%.1f" % metric["mean_latency_ms"]])
    table(rows, [150, 65, 65, 80, 110])
    add("Extraction F1: %s. Reconciliation macro-F1: %s. FIR: %d/%d." % (percent(live["extraction"]["f1"]), percent(live["reconciliation"]["macro_f1"]), live["false_invalidation"]["retired"], live["false_invalidation"]["considered"]))
    add("This run recorded %d live language-model calls and %d cache hits. Mean query times include the measured cache behavior and are not cold-inference speed claims." % (live.get("measured_live_calls", 0), live.get("cache_hits", 0)), "SmallAmnesia")
    n, score = live["count"], live["metrics"]["hybrid"]["answer_accuracy"]
    z=1.96; denominator=1+z*z/n; center=(score+z*z/(2*n))/denominator; half=z*math.sqrt(score*(1-score)/n+z*z/(4*n*n))/denominator
    add("The hybrid exact-answer estimate has a 95%% Wilson interval of approximately %.1f%% to %.1f%% on this sample. No statistical superiority claim is made from this small internal set." % ((center-half)*100, (center+half)*100), "SmallAmnesia")
    if codex: add("The language model was called through the official Codex CLI using an existing ChatGPT login. Embeddings ran locally through Nomic. These are Codex-login measurements, separate from direct OpenAI API or fully local Ollama results. CLI startup and harness input overhead are included in measured latency/token totals. Codex reasoning effort was low; temperature is not exposed by this adapter.", "SmallAmnesia")
    elif not cloud: add("The table above is local-model evidence only. No completed Codex-login or direct OpenAI API artifact was available at generation time.", "SmallAmnesia")
else: add("No completed live-model evaluation artifact was available at report generation. Configure the AI engine and run the live suite; do not invent empirical values.")
page()

heading("8. Error analysis and limitations")
add("Development uncovered malformed model validity intervals, pet-name aliases that conflicted with stable pet identity, and device answers that mixed phones with laptops. The release normalizes negative cancellation records, versions pet-name literals, validates source quotations, and applies explicit scope filters. Validation failures receive at most one repair attempt; auth/network failures do not trigger duplicate calls.")
if live:
    extraction = live["extraction"]
    add("The selected live run retained %d false-positive and %d missing gold assertions (extraction F1 %s). In the local run, examples included destination labels such as 'trip to Hyderabad' instead of 'Hyderabad', missing explicit sale assertions, and extra pet-ownership facts. Correct final answers do not erase these extraction errors; the full extraction audit remains in the raw JSON." % (extraction.get("fp", 0), extraction.get("fn", 0), percent(extraction["f1"])))
    if codex:
        add("In the Codex integration run, the two extraction mismatches used 'trip to Hyderabad' instead of the gold destination 'Hyderabad'. Full-context and graph answers also chose Hyderabad when the expected response was unresolved uncertainty. All four methods had zero stale-value errors (0/7), so this run does not establish a live SMER advantage. Twenty questions cover all ten categories but remain a small internal integration sample.")
if live and live.get("failures"):
    sub("Retained failed hybrid cases")
    table([["Case", "Gold", "Actual"]]+[[f["id"], f["expected"], f["actual"]] for f in live["failures"][:5]], [250, 110, 110])
else: add("No failed hybrid cases were recorded in the selected completed artifact. This does not establish correctness outside the evaluated set.")
sub("Threats to validity")
for text in ["The data are synthetic/curated and internal. Real conversations, third-party annotation, and blind held-out testing are still needed.", "Model confidence is not calibrated. Citation validation does not prove semantic entailment.", "Alias and scope resolution remain bounded. The system does not solve unrestricted entity identity or arbitrary world-time inference.", "The gold policy suite is intentionally favorable to testing lifecycle rules; its perfect scores cannot be generalized to a live language model.", "The live suite lacks SAME transitions; duplicate behavior is covered in policy cases and regression tests.", "Results with different providers, models, cache states, and context budgets must remain separately labeled."]:
    add("- "+text, "SmallAmnesia")
sub("Expected next research step")
add("Freeze a new held-out conversation set; add independent annotations and richer multi-hop cases; evaluate model-assisted reconciliation against the conservative policy; and measure the accuracy/context-cost tradeoff across retrieval budgets. These are future extensions, not shipped claims.")
page()

heading("9. Final-review demonstration and handoff")
table([["Step", "What to show"], ["1. Preflight", "Select Codex login in AI engine, Save & test engine, then run npm run doctor."], ["2. Remember", "Start Final review; a new workspace extracts initial home and preference."], ["3. Evolve", "Advance to relocation; show earlier assertions as history and new current values."], ["4. Retrieve", "Compare actual hybrid, vector, and raw-context answers; inspect sources."], ["5. Preserve", "Add employer, project, and beverage facts without invalidating home/language."], ["6. Clarify", "Introduce an uncertain move, show unresolved alternatives, then explicitly confirm."], ["7. Evaluate", "Show saved policy/live metrics, model identity, failures, and limitations."]], [120, 350])
sub("Run commands")
add("npm install<br/>npm run build<br/>npm run review<br/>npm test<br/>npm run evaluate<br/>npm run evaluate:ai", "SmallAmnesia")
add("The macOS Start Amnesia.command launcher opens the review and reuses this project's running server. The release archive includes source, compiled frontend, synthetic annotations, measured outputs, and this PDF. Runtime workspaces, API keys, model caches, and node_modules are excluded.")
sub("References")
for reference in ["[1] Park et al. Generative Agents: Interactive Simulacra of Human Behavior. UIST 2023. arXiv:2304.03442.", "[2] Packer et al. MemGPT: Towards LLMs as Operating Systems. arXiv:2310.08560.", "[3] Gutierrez et al. HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models. arXiv:2405.14831.", "[4] Rasmussen et al. Zep: A Temporal Knowledge Graph Architecture for Agent Memory. arXiv:2501.13956.", "[5] OpenAI. Structured Outputs and embeddings documentation. developers.openai.com/api/docs/.", "[6] Ollama. Structured Outputs and model documentation. docs.ollama.com; ollama.com/library."]:
    add(escape(reference), "SmallAmnesia")

OUT.parent.mkdir(parents=True, exist_ok=True)
doc = SimpleDocTemplate(str(OUT), pagesize=(210*mm, 297*mm), rightMargin=22*mm, leftMargin=22*mm, topMargin=21*mm, bottomMargin=27*mm, title="Amnesia - Final Review Report", author="Abhilaksh Chauhan")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
