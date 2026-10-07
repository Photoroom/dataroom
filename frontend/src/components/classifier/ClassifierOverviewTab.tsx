import React from "react";
import { Classifier } from "../../api/client.schemas";
import { Card } from "../common/Card";

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <>
    <dt className="opacity-60">{label}</dt>
    <dd className="min-w-0 break-words">{children}</dd>
  </>
);

/** What this classifier is: who made it, what it learns from, how big it is. */
export const ClassifierOverviewTab: React.FC<{ classifier: Classifier }> = ({ classifier }) => {
  const counts = classifier.counts;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="flex-col gap-1 p-4">
          <span className="text-2xl font-bold tabular-nums text-emerald-700 dark:text-emerald-400">{counts.pos}</span>
          <span className="text-xs opacity-60">positive annotations</span>
          <span className="text-[11px] opacity-40 tabular-nums">
            {counts.main_pos} main + {counts.extra_pos} additional
          </span>
        </Card>
        <Card className="flex-col gap-1 p-4">
          <span className="text-2xl font-bold tabular-nums text-rose-700 dark:text-rose-400">{counts.neg}</span>
          <span className="text-xs opacity-60">negative annotations</span>
          <span className="text-[11px] opacity-40 tabular-nums">
            {counts.main_neg} main + {counts.extra_neg} additional
          </span>
        </Card>
        <Card className="flex-col gap-1 p-4">
          <span className="text-2xl font-bold tabular-nums">v{classifier.version}</span>
          <span className="text-xs opacity-60">{classifier.is_frozen ? "locked" : "open for edits"}</span>
        </Card>
        <Card className="flex-col gap-1 p-4">
          <span className="text-sm font-mono truncate">{classifier.embedding_space || "-"}</span>
          <span className="text-xs opacity-60">embedding space</span>
        </Card>
      </div>

      <Card className="flex-col gap-3 p-4">
        <dl className="grid grid-cols-[10rem_1fr] gap-y-2 text-sm">
          <Row label="Slug">
            <span className="font-mono">{classifier.slug_version}</span>
          </Row>
          <Row label="Owner">{classifier.author?.email ?? "-"}</Row>
          <Row label="Description">{classifier.description || <span className="opacity-40">none</span>}</Row>
          <Row label="Created">{new Date(classifier.date_created).toLocaleString()}</Row>
          <Row label="Last change">{new Date(classifier.date_updated).toLocaleString()}</Row>
        </dl>
      </Card>
    </div>
  );
};
