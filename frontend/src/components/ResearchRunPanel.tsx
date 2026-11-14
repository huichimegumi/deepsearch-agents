import {
  CheckCircleFilled,
  ExclamationCircleFilled,
  LoadingOutlined,
  MinusCircleOutlined
} from "@ant-design/icons";
import type { MonitorMessage } from "../types";

const PHASES = [
  { key: "clarify_and_brief", label: "研究简报" },
  { key: "supervisor_research", label: "并行研究" },
  { key: "evidence_compression", label: "证据压缩" },
  { key: "final_report", label: "写作" }
];

type StepState = "pending" | "running" | "done" | "failed";

interface Researcher {
  index: number;
  subquestions: string[];
  done: boolean;
  answer: string;
}

export interface WebSource {
  evidence_id: string;
  url: string;
  title: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function traceEvent(events: MonitorMessage[]): MonitorMessage | undefined {
  return events.find((event) => event.event === "research_trace_complete");
}

export function getWebSources(events: MonitorMessage[]): WebSource[] {
  const sources = traceEvent(events)?.data.sources;
  if (!Array.isArray(sources)) {
    return [];
  }
  return sources
    .map((item) => asRecord(item))
    .filter((item) => typeof item.evidence_id === "string" && typeof item.url === "string")
    .map((item) => ({
      evidence_id: String(item.evidence_id),
      url: String(item.url),
      title: typeof item.title === "string" ? item.title : ""
    }));
}

/** 把报告里的 [evidence_id] 换成带编号的原文链接，并在末尾附来源列表。 */
export function linkCitations(markdown: string, sources: WebSource[]): string {
  if (sources.length === 0) {
    return markdown;
  }
  const byId = new Map(sources.map((source) => [source.evidence_id.toLowerCase(), source]));
  const cited: WebSource[] = [];
  const linked = markdown.replace(/\s?\[(ev[0-9]+_[a-z0-9_-]+)\]/gi, (match, id: string) => {
    const source = byId.get(id.toLowerCase());
    if (!source) {
      return match;
    }
    let position = cited.indexOf(source);
    if (position === -1) {
      cited.push(source);
      position = cited.length - 1;
    }
    return ` [\\[${position + 1}\\]](${source.url})`;
  });
  if (cited.length === 0) {
    return markdown;
  }
  const list = cited
    .map((source, index) => {
      const title = (source.title || source.url).replace(/[[\]]/g, "");
      return `${index + 1}. [${title}](${source.url})`;
    })
    .join("\n");
  return `${linked}\n\n---\n\n**来源**\n\n${list}`;
}

function phaseStates(events: MonitorMessage[], isRunning: boolean): Record<string, StepState> {
  const states: Record<string, StepState> = {};
  events.forEach((event) => {
    if (event.event !== "research_phase") {
      return;
    }
    const key = String(event.data.phase_key || "");
    const status = String(event.data.status || "");
    if (status === "start") {
      states[key] = "running";
    } else if (status === "end") {
      states[key] = "done";
    } else {
      states[key] = "failed";
    }
  });
  if (!isRunning) {
    Object.keys(states).forEach((key) => {
      if (states[key] === "running") {
        states[key] = "failed";
      }
    });
  }
  return states;
}

function researchers(events: MonitorMessage[], researchFinished: boolean): Researcher[] {
  const byIndex = new Map<number, Researcher>();
  events.forEach((event) => {
    if (event.event === "assistant_call") {
      const args = asRecord(event.data.args);
      const index = asNumber(args.index);
      if (index === null) {
        return;
      }
      byIndex.set(index, {
        index,
        subquestions: String(args.description || "")
          .split("\n")
          .map((line) => line.replace(/^-\s*/, "").trim())
          .filter(Boolean),
        done: false,
        answer: ""
      });
    }
    if (event.event === "researcher_done") {
      const index = asNumber(event.data.index);
      const researcher = index === null ? undefined : byIndex.get(index);
      if (researcher) {
        researcher.done = true;
        researcher.answer = String(event.data.answer || "");
      }
    }
  });
  return [...byIndex.values()]
    .sort((left, right) => left.index - right.index)
    .map((researcher) => ({ ...researcher, done: researcher.done || researchFinished }));
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "done") {
    return <CheckCircleFilled aria-hidden />;
  }
  if (state === "running") {
    return <LoadingOutlined aria-hidden spin />;
  }
  if (state === "failed") {
    return <ExclamationCircleFilled aria-hidden />;
  }
  return <MinusCircleOutlined aria-hidden />;
}

function RunSummary({ events }: { events: MonitorMessage[] }) {
  const trace = traceEvent(events);
  if (!trace) {
    return null;
  }
  const metrics = asRecord(trace.data.metrics);
  const budget = asRecord(trace.data.budget);
  const usage = asRecord(budget.usage);
  const limits = asRecord(budget.limits);
  const elapsed = asNumber(trace.data.elapsed_ms);
  const degraded = trace.data.degraded === true || trace.data.status !== "completed";

  const withLimit = (used: unknown, limit: unknown) => {
    const usedNumber = asNumber(used);
    const limitNumber = asNumber(limit);
    if (usedNumber === null) {
      return "—";
    }
    return limitNumber === null ? String(usedNumber) : `${usedNumber} / ${limitNumber}`;
  };

  const items = [
    { label: "用时", value: elapsed === null ? "—" : `${(elapsed / 1000).toFixed(1)} 秒` },
    { label: "搜索查询", value: withLimit(usage.search_queries, limits.max_search_queries) },
    { label: "抓取页面", value: withLimit(usage.fetched_pages, limits.max_fetched_pages) },
    { label: "模型调用", value: withLimit(usage.llm_calls, limits.max_llm_calls) },
    { label: "登记证据", value: withLimit(metrics.evidence_records, null) },
    { label: "报告引用证据", value: withLimit(metrics.report_cited_evidence_records, null) },
    {
      label: "输入 token",
      value: asNumber(metrics.input_tokens)?.toLocaleString("zh-CN") ?? "—"
    }
  ];

  return (
    <div className="run-summary" aria-label="运行轨迹摘要">
      <span className={degraded ? "run-status run-status--degraded" : "run-status"}>
        {degraded ? "降级完成" : "正常完成"}
      </span>
      {items.map((item) => (
        <span className="run-metric" key={item.label}>
          <small>{item.label}</small>
          <strong>{item.value}</strong>
        </span>
      ))}
    </div>
  );
}

export function hasResearchRun(events: MonitorMessage[]): boolean {
  return events.some(
    (event) =>
      event.event === "research_phase" &&
      PHASES.some((phase) => phase.key === event.data.phase_key)
  );
}

export function ResearchRunPanel({
  events,
  isRunning
}: {
  events: MonitorMessage[];
  isRunning: boolean;
}) {
  const states = phaseStates(events, isRunning);
  const researchState = states.supervisor_research;
  const team = researchers(events, researchState === "done" || researchState === "failed");

  return (
    <section className="run-panel" aria-label="研究流程">
      <ol className="run-steps">
        {PHASES.map((phase) => {
          const state = states[phase.key] || "pending";
          return (
            <li className={`run-step run-step--${state}`} key={phase.key}>
              <StepIcon state={state} />
              <span>{phase.label}</span>
            </li>
          );
        })}
      </ol>

      {team.length > 0 ? (
        <div className="researcher-grid">
          {team.map((researcher) => (
            <article
              className={researcher.done ? "researcher-card researcher-card--done" : "researcher-card"}
              key={researcher.index}
            >
              <header>
                <strong>研究员 {researcher.index}</strong>
                <span>
                  {researcher.done ? (
                    <>
                      <CheckCircleFilled aria-hidden /> 完成
                    </>
                  ) : (
                    <>
                      <LoadingOutlined aria-hidden spin /> 搜索并阅读
                    </>
                  )}
                </span>
              </header>
              {researcher.subquestions.map((subquestion) => (
                <p key={subquestion}>{subquestion}</p>
              ))}
              {researcher.answer ? (
                <details>
                  <summary>查看结论</summary>
                  <p>{researcher.answer}</p>
                </details>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      <RunSummary events={events} />
    </section>
  );
}
