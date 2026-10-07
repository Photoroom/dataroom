import React from "react";
import { Link } from "react-router-dom";
import { useClassifiersRunsList } from "../../api/client";
import { Classifier, ClassifierApplyRun } from "../../api/client.schemas";
import { Card } from "../common/Card";
import { isRunActive, pollWhileRunning } from "./runs";

const targetLabel = (run: ClassifierApplyRun) => `${run.target_type} ${run.target_value}`;

/** Past runs of this version, and where their scores ended up. */
export const ClassifierResultsTab: React.FC<{ classifier: Classifier }> = ({ classifier }) => {
  const { data: runs = [] } = useClassifiersRunsList(classifier.slug_version, undefined, {
    query: { refetchInterval: pollWhileRunning },
  });

  return (
    <div className="flex flex-col gap-4">
      {runs.length === 0 && <p className="text-sm opacity-50">No runs yet. Apply this version to make one.</p>}
      {runs.map(run => (
        <Card key={run.id} className="flex-col gap-2 p-4">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-mono text-xs opacity-60" title={run.id}>
              {run.id.slice(0, 8)}
            </span>
            <span>{targetLabel(run)}</span>
            <div className="flex-1" />
            {run.dagster_run_url && (
              <a
                href={run.dagster_run_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs px-2 py-0.5 rounded-md bg-brand-500/10 text-brand-700 hover:bg-brand-500/20 dark:bg-brand-400/15 dark:text-brand-300 dark:hover:bg-brand-400/25"
                title="Open this run in the Dagster UI"
              >
                view live ↗
              </a>
            )}
            <span className="text-xs opacity-60">{run.status}</span>
          </div>
          {isRunActive(run) && run.total ? (
            <div className="h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
              <div
                className="h-full bg-brand-500 transition-all"
                style={{ width: `${Math.min(100, (100 * run.processed) / run.total)}%` }}
              />
            </div>
          ) : null}
          <div className="text-xs opacity-60 tabular-nums">
            {run.processed}/{run.total ?? "?"} scored, started {new Date(run.date_created).toLocaleString()}
          </div>
          {run.status === "failed" && run.error && (
            <p className="text-xs text-red-600 dark:text-red-400 break-all">{run.error}</p>
          )}
          {run.status === "completed" && (
            <div className="flex items-center gap-2 flex-wrap">
              <Link
                to={`/images?classifications=${encodeURIComponent(`${classifier.slug_version}__gte:0.5`)}`}
                className="text-xs px-2 py-0.5 rounded-md bg-brand-500/10 text-brand-700 hover:bg-brand-500/20 dark:bg-brand-400/15 dark:text-brand-300 dark:hover:bg-brand-400/25"
              >
                Browse scored images
              </Link>
              <p className="text-xs opacity-60">
                Scores are on the images as{" "}
                <code className="font-mono">classifications[&quot;{classifier.slug_version}&quot;]</code>
              </p>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
};
