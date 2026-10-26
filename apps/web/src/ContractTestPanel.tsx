import report from "../../../reports/contract-model-test.json";
import replay from "../../../reports/contract-model-test-standalone-replay.json";

const count = (value: number) => value.toLocaleString("en-CA");
const percent = (value: number | null) =>
  value === null ? "Not measured" : `${(value * 100).toFixed(1)}%`;

export function ContractTestPanel() {
  const model = report.results;
  const reference = report.constant_not_mentioned_reference;
  const admitted =
    report.task === "contractnli-test-v1" &&
    report.replay_matches_recorded_results &&
    replay.results_equal &&
    replay.reference_equal &&
    report.protocol_sha256 === replay.protocol_sha256 &&
    report.observations.sha256 === replay.observations_sha256 &&
    model.documents === replay.documents &&
    model.claims === replay.claims;
  if (!admitted)
    return (
      <section className="evaluation-explainer" role="note">
        The contract test and its replay record do not match. No comparison is
        shown.
      </section>
    );
  return (
    <section
      className="evaluation-explainer"
      aria-label="External contract test"
    >
      <h2>A separate test on {count(model.documents)} contracts</h2>
      <p>
        The examples above are fictional. This test uses ContractNLI’s
        externally written annotations for non-disclosure agreements. The model
        classifies each claim as supported, contradicted or not mentioned, then
        selects the passages needed to explain its answer.
      </p>
      <div className="public-table">
        <table>
          <caption>
            All {count(model.claims)} claims, with the rules fixed before the
            test data was loaded
          </caption>
          <thead>
            <tr>
              <th>What counted as right</th>
              <th>Always answer “not mentioned”</th>
              <th>Claude Haiku 4.5</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Correct label</th>
              <td>{percent(reference.label_accuracy)}</td>
              <td>{percent(model.label_accuracy)}</td>
            </tr>
            <tr>
              <th scope="row">Correct label and complete evidence</th>
              <td>{percent(reference.joint_label_and_exact_evidence)}</td>
              <td>{percent(model.joint_label_and_exact_evidence)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Only {model.per_class.Contradiction.correct} of{" "}
        {model.per_class.Contradiction.support} contradictions received the
        right label. The model called {model.confusion.Contradiction.Entailment}{" "}
        of them supported. All {model.missing_predictions} missing answers
        stayed in the score. A reviewer still needs to check the text before
        accepting a finding.
      </p>
      <details className="limits">
        <summary>How the contract test was run</summary>
        <p>
          The model, prompt, scoring code and failure rules were fixed before
          this project loaded the test split. Every contract was included, with
          no retry or tuning after seeing test answers. The saved responses were
          independently rescored by CHAOSLAB without ATLAS or another model
          call.
        </p>
        <dl>
          <dt>Macro F1, the primary measure</dt>
          <dd>
            {model.macro_label_f1.toFixed(3)}; each label has equal weight
          </dd>
          <dt>Evidence precision</dt>
          <dd>{percent(model.evidence.micro_precision)}</dd>
          <dt>Evidence recall</dt>
          <dd>{percent(model.evidence.micro_recall)}</dd>
        </dl>
        <p>
          Evidence measures cover the {count(model.evidence.eligible_claims)}{" "}
          claims that require passages. The joint score also includes
          not-mentioned claims, whose expected evidence is empty. This public
          dataset may have appeared in model training. It does not measure a
          complete RFP review or establish legal correctness.
        </p>
        <p>
          <a href="https://github.com/harshituppala/atlas-chaoslab/blob/main/docs/contractnli-evaluation.md#frozen-test-result--october-26">
            Read the results and error analysis
          </a>
          {" · "}
          <a href="https://github.com/harshituppala/atlas-chaoslab/blob/main/reports/contract-model-test-standalone-replay.json">
            Check the independent replay record
          </a>
        </p>
      </details>
    </section>
  );
}
