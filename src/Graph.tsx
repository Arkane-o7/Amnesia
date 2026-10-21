import { useState } from "react";
import {
  Focus,
  Minus,
  Plus,
  Network,
  History,
  ArrowUpRight,
} from "lucide-react";
import type { Fact, State } from "./types";
import { date, relations } from "./types";

export function Graph({
  state,
  onSelect,
  selected,
}: {
  state: State;
  onSelect: (f: Fact) => void;
  selected?: string;
}) {
  const [history, setHistory] = useState(true);
  const [view, setView] = useState<"graph" | "timeline">("graph");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [drag, setDrag] = useState<{
    x: number;
    y: number;
    px: number;
    py: number;
  } | null>(null);
  const visible = state.facts.filter(
    (f) => history || ["active", "unresolved"].includes(f.effective_status),
  );
  const facts = visible.slice(-24);
  const subjects = [
    ...new Map(facts.map((f) => [f.subject_id, f.subject])).entries(),
  ];
  const positions = new Map(
    subjects.map(([id], i) => [
      id,
      { x: i === 0 ? 362 : 125 + i * 30, y: i === 0 ? 235 : 320 + i * 25 },
    ]),
  );
  const nodes = facts.map((fact, i) => {
    const angle =
      -Math.PI * 0.78 + (i / Math.max(facts.length, 1)) * Math.PI * 2;
    return {
      fact,
      x: 362 + Math.cos(angle) * 239,
      y: 235 + Math.sin(angle) * 154,
    };
  });
  return (
    <section className="panel graph-panel">
      <div className="panel-heading">
        <div>
          <h2>
            A living knowledge graph{" "}
            <span className="tiny-count">{state.entities.length}</span>
          </h2>
          <p>Connections change. Their history stays.</p>
        </div>
        <div className="segmented icon-tabs">
          <button
            className={view === "graph" ? "selected" : ""}
            onClick={() => setView("graph")}
            aria-label="Graph view"
          >
            <Network size={15} />
          </button>
          <button
            className={view === "timeline" ? "selected" : ""}
            onClick={() => setView("timeline")}
            aria-label="Timeline view"
          >
            <History size={15} />
          </button>
        </div>
      </div>
      <div className="graph-canvas">
        <div className="canvas-top">
          <span className="canvas-label">
            <span className="live-dot" />{" "}
            {view === "graph" ? "MEMORY NETWORK" : "EVOLUTION TIMELINE"}
          </span>
          <label className="switch-label">
            <input
              type="checkbox"
              checked={history}
              onChange={(e) => setHistory(e.target.checked)}
            />
            <span className="switch" />
            Show history
          </label>
        </div>
        {view === "graph" ? (
          <>
            <svg
              className={drag ? "network dragging" : "network"}
              viewBox="0 0 724 470"
              role="group"
              aria-label="Interactive memory knowledge graph"
              onPointerDown={(e) => {
                if (e.target === e.currentTarget) {
                  e.currentTarget.setPointerCapture(e.pointerId);
                  setDrag({ x: e.clientX, y: e.clientY, px: pan.x, py: pan.y });
                }
              }}
              onPointerMove={(e) => {
                if (drag)
                  setPan({
                    x: drag.px + (e.clientX - drag.x),
                    y: drag.py + (e.clientY - drag.y),
                  });
              }}
              onPointerUp={() => setDrag(null)}
              onPointerCancel={() => setDrag(null)}
            >
              <defs>
                <marker
                  id="arrow"
                  markerWidth="6"
                  markerHeight="6"
                  refX="5"
                  refY="3"
                  orient="auto"
                >
                  <path d="M0,0 L6,3 L0,6" fill="#b0bacd" />
                </marker>
              </defs>
              <g
                transform={`translate(${pan.x + 362 * (1 - zoom)} ${pan.y + 235 * (1 - zoom)}) scale(${zoom})`}
              >
                {nodes.map(({ fact, x, y }) => {
                  const from = positions.get(fact.subject_id)!;
                  const faded = !["active", "unresolved"].includes(
                    fact.effective_status,
                  );
                  return (
                    <g
                      key={`edge-${fact.id}`}
                      className={faded ? "graph-edge historical" : "graph-edge"}
                    >
                      <path
                        d={`M ${from.x} ${from.y} Q ${(from.x + x) / 2 + (y - from.y) * 0.08} ${(from.y + y) / 2 - 12} ${x} ${y}`}
                        fill="none"
                        stroke={faded ? "#d4d8e4" : "#bcc5d9"}
                        strokeWidth="1.35"
                        strokeDasharray={faded ? "4 5" : undefined}
                      />
                      <rect
                        x={(from.x + x) / 2 - 35}
                        y={(from.y + y) / 2 - 19}
                        width="70"
                        height="17"
                        rx="7"
                        fill="#fcfcfe"
                      />
                      <text
                        x={(from.x + x) / 2}
                        y={(from.y + y) / 2 - 7}
                        textAnchor="middle"
                      >
                        {relations[fact.relation]}
                      </text>
                    </g>
                  );
                })}
                {subjects.map(([id, name]) => {
                  const p = positions.get(id)!;
                  return (
                    <g
                      key={id}
                      className="subject-node"
                      transform={`translate(${p.x} ${p.y})`}
                    >
                      <circle r="45" fill="#7066e9" opacity=".06" />
                      <circle
                        r="34"
                        fill={name === "You" ? "#756be7" : "#eef0fb"}
                        stroke={name === "You" ? "#756be7" : "#c2c7e7"}
                      />
                      <text
                        textAnchor="middle"
                        y="5"
                        fill={name === "You" ? "white" : "#666998"}
                      >
                        {name === "You" ? "You" : name.replace("Your ", "")}
                      </text>
                      <text
                        textAnchor="middle"
                        y="61"
                        className="subject-caption"
                      >
                        {name === "You" ? "PRIMARY ENTITY" : "RELATED ENTITY"}
                      </text>
                    </g>
                  );
                })}
                {nodes.map(({ fact, x, y }) => {
                  const faded = !["active", "unresolved"].includes(
                    fact.effective_status,
                  );
                  const width = Math.max(
                    88,
                    Math.min(166, fact.value.length * 7 + 39),
                  );
                  return (
                    <g
                      key={fact.id}
                      role="button"
                      tabIndex={0}
                      aria-label={`${fact.value}, ${relations[fact.relation]}, ${fact.effective_status}`}
                      onClick={() => onSelect(fact)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onSelect(fact);
                        }
                      }}
                      className={`object-node ${faded ? "historical" : ""} ${selected === fact.id ? "chosen" : ""}`}
                      transform={`translate(${x} ${y})`}
                    >
                      <rect
                        x={-width / 2}
                        y="-22"
                        width={width}
                        height="44"
                        rx="11"
                      />
                      <circle
                        cx={-width / 2 + 17}
                        cy="0"
                        r="3.5"
                        className={`dot-${fact.effective_status}`}
                      />
                      <text x="5" y="5" textAnchor="middle">
                        {fact.value.length > 18
                          ? fact.value.slice(0, 17) + "…"
                          : fact.value}
                      </text>
                      <text textAnchor="middle" y="38" className="node-state">
                        {fact.effective_status === "active"
                          ? "CURRENT"
                          : fact.effective_status.toUpperCase()}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
            {!facts.length && (
              <div className="graph-empty">
                <Network size={30} />
                <h3>Your graph starts with a fact.</h3>
                <p>Try “I live in Hyderabad” in the conversation.</p>
              </div>
            )}
            {visible.length > 24 && (
              <span className="graph-overflow">
                Showing the latest 24 of {visible.length} assertions. View all
                in Memory ledger.
              </span>
            )}
            <div className="zoom-controls">
              <button
                aria-label="Zoom out"
                onClick={() => setZoom((z) => Math.max(0.5, z - 0.15))}
              >
                <Minus size={14} />
              </button>
              <span>{Math.round(zoom * 100)}%</span>
              <button
                aria-label="Zoom in"
                onClick={() => setZoom((z) => Math.min(1.75, z + 0.15))}
              >
                <Plus size={14} />
              </button>
              <i />
              <button
                aria-label="Fit graph"
                onClick={() => {
                  setZoom(1);
                  setPan({ x: 0, y: 0 });
                }}
              >
                <Focus size={15} />
              </button>
            </div>
          </>
        ) : (
          <div className="evolution-timeline">
            {state.events
              .filter((e) => e.role === "user")
              .map((event) => (
                <div className="timeline-entry" key={event.id}>
                  <span className="timeline-dot" />
                  <time>
                    {date(event.observed_at)} ·{" "}
                    {
                      state.sessions.find((s) => s.id === event.session_id)
                        ?.name
                    }
                  </time>
                  <p>{event.text}</p>
                  <div className="tag-row">
                    {state.decisions
                      .filter((d) => d.event_id === event.id)
                      .map((d) => (
                        <button
                          key={d.id}
                          className="decision-tag"
                          onClick={() => {
                            const f = state.facts.find(
                              (f) => f.id === d.fact_id,
                            );
                            if (f) onSelect(f);
                          }}
                        >
                          {d.label.toLowerCase()} <ArrowUpRight size={11} />
                        </button>
                      ))}
                  </div>
                </div>
              ))}
            {!state.events.length && (
              <p className="empty-copy">Add a memory to start your timeline.</p>
            )}
          </div>
        )}
        <div className="graph-legend">
          <span>
            <i className="legend-dot active" />
            Current
          </span>
          <span>
            <i className="legend-dot superseded" />
            Superseded
          </span>
          <span>
            <i className="legend-dot unresolved" />
            Unresolved
          </span>
          <span className="legend-hint">
            Select a memory to inspect its evidence <ArrowUpRight size={12} />
          </span>
        </div>
      </div>
    </section>
  );
}
