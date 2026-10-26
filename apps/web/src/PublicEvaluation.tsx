import { useState } from "react";
import { ContractTestPanel } from "./ContractTestPanel";
import { PublicHeader } from "./PublicHeader";
import { ScenarioPanel } from "./ScenarioPanel";
import scenarioBaseline from "../../../reports/scenarios-baseline.json";
import scenarioModel from "../../../reports/scenarios-live-v4.json";
import transferBaseline from "../../../reports/reasoning-transfer-baseline.json";
import transferModel from "../../../reports/reasoning-transfer-live-v4.json";
import transferInputs from "../../../datasets/reasoning-transfer.json";

const relation = (value: string) =>
  ({
    supported: "Evidence supports the requirement",
    contradicted: "Evidence contradicts the requirement",
    insufficient: "Not enough evidence",
    invalid_extraction: "No valid requirement extracted",
  })[value] ?? value;

export function PublicEvaluation() {
  const failures = transferModel.results.filter((item) => !item.passed);
  const [selected, setSelected] = useState(failures[0]?.id ?? "");
  const result = failures.find((item) => item.id === selected);
  const source = transferInputs.cases.find((item) => item.id === selected);
  const comparable =
    transferBaseline.dataset_sha256 === transferModel.dataset_sha256 &&
    transferBaseline.summary.cases === transferInputs.cases.length;
  return (
    <>
      <a className="skip" href="#content">
        Skip to content
      </a>
      <PublicHeader active="evaluation" />
      <main id="content" className="public-evaluation">
        <section className="intro">
          <div>
            <p className="eyebrow">CHAOSLAB · RECORDED EXPERIMENTS</p>
            <h1>Does the model make the review better?</h1>
            <p>
              A plausible answer is not enough. CHAOSLAB compares a system’s
              answers with expected results, checks the sources and keeps failed
              cases in the report. ATLAS is one system it evaluates.
            </p>
          </div>
          <aside>
            <strong>Saved results, available to inspect</strong>
            <p>
              The worked examples come from earlier executions on fictional
              documents. Opening this page makes no model request and starts no
              evaluation. The interactive review sample runs separately.
            </p>
          </aside>
        </section>
        <section className="evaluation-explainer">
          <h2>Start with the same task, using two approaches</h2>
          <p>
            The rule-based baseline looks for patterns and related text. The
            recorded model workflow uses Claude Haiku 4.5 through Amazon
            Bedrock. Both are judged against the same expected requirements and
            evidence. A complete review passes only when every requirement
            passes.
          </p>
        </section>
        <ScenarioPanel baseline={scenarioBaseline} live={scenarioModel} />
        <section className="evaluation-explainer">
          <h2>Now try twelve different cases</h2>
          <p>
            This separate set checks deletion deadlines, availability promises,
            access reviews and incident notices. It was authored after the model
            prompt was fixed, but by the same developer. It is not a blinded
            independent test or a measure of accuracy on customer contracts.
          </p>
          {comparable ? (
            <div className="public-table">
              <table>
                <caption>Recorded results on the same twelve cases</caption>
                <thead>
                  <tr>
                    <th>Approach</th>
                    <th>Cases passed</th>
                    <th>Cases not run</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">Rule-based baseline</th>
                    <td>
                      {transferBaseline.summary.cases_passed} /{" "}
                      {transferBaseline.summary.cases}
                    </td>
                    <td>0</td>
                  </tr>
                  <tr>
                    <th scope="row">Recorded model workflow</th>
                    <td>
                      {transferModel.summary.cases_passed} /{" "}
                      {transferModel.evaluated_cases}
                    </td>
                    <td>{transferModel.not_run_cases}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          ) : (
            <p role="note">
              The dataset versions differ. These runs cannot be directly
              compared.
            </p>
          )}
        </section>
        <section
          className="failure-example"
          aria-label="Inspect a recorded model failure"
        >
          <div>
            <p className="eyebrow">THE MODEL STILL GETS THINGS WRONG</p>
            <h2>Open a failed case</h2>
            <p>
              A correct source location does not guarantee a correct decision.
              Compare the original requirement and evidence with the model’s
              recorded answer.
            </p>
            <label>
              Failed case
              <select
                value={selected}
                onChange={(event) => setSelected(event.target.value)}
              >
                {failures.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id === "deletion-1"
                      ? "Deletion deadline: a faster promise was misread"
                      : item.id === "availability-3"
                        ? "Availability: no valid requirement extracted"
                        : item.id}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {source && result ? (
            <div className="recorded-answer">
              <h3>Buyer’s requirement</h3>
              <blockquote>{source.requirement}</blockquote>
              <h3>Supplier’s evidence</h3>
              <blockquote>{source.evidence}</blockquote>
              <dl>
                <dt>Expected result</dt>
                <dd>{relation(result.expected)}</dd>
                <dt>Recorded model result</dt>
                <dd>{relation(result.predicted)}</dd>
                <dt>Source citation</dt>
                <dd>
                  {result.citation_integrity === true
                    ? "Matched the source text, even though the decision was wrong"
                    : result.citation_integrity === false
                      ? "Failed source validation"
                      : "Not available for this failed extraction"}
                </dd>
              </dl>
            </div>
          ) : (
            <p role="note">
              The source case is unavailable; no explanation is inferred.
            </p>
          )}
        </section>
        <ContractTestPanel />
        <details className="limits">
          <summary>What these results do and do not establish</summary>
          <p>
            The fictional examples use small authored development sets. Their
            counts cannot be combined into one accuracy score, and passing them
            does not prove general reliability or legal compliance. The first
            comparison has three scenarios and nine requirements; the second has
            twelve single-requirement cases. Human approval remains a separate
            step.
          </p>
          <p>
            CHAOSLAB also has failure-injection, recovery and independently
            installable evaluation tools. This page presents saved
            answer-quality evidence; it does not run those tools or establish
            production uptime.
          </p>
        </details>
        <footer>
          <a href="?view=review">Try the ATLAS review sample</a>
          <a href="https://github.com/harshituppala/atlas-chaoslab/tree/main/src/chaoslab">
            CHAOSLAB source and run instructions
          </a>
        </footer>
      </main>
    </>
  );
}
