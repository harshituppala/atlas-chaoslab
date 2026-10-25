export function PublicHeader({ active }: { active: "review" | "evaluation" }) {
  return (
    <header className="lab-header">
      <a href="?view=review" className="brand">
        <b>{active === "review" ? "A" : "C"}</b>
        <span>
          {active === "review" ? "ATLAS" : "CHAOSLAB"}
          <small>
            {active === "review" ? "REQUIREMENTS REVIEW" : "EVALUATION"}
          </small>
        </span>
      </a>
      <nav aria-label="Projects">
        <a
          href="?view=review"
          aria-current={active === "review" ? "page" : undefined}
        >
          Review sample
        </a>
        <a
          href="?view=evaluation"
          aria-current={active === "evaluation" ? "page" : undefined}
        >
          Evaluation results
        </a>
      </nav>
    </header>
  );
}
