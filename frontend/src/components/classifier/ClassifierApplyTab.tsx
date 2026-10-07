import React, { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";
import {
  getClassifiersRunsListQueryKey,
  useClassifiersApplyCreate,
  useClassifiersRunsList,
  useClassifiersTrainingsList,
  useImagesCountRetrieve,
} from "../../api/client";
import { Classifier, ImagesCountRetrieveParams, TargetTypeEnum } from "../../api/client.schemas";
import { Card } from "../common/Card";
import { TargetCombobox } from "./TargetCombobox";
import { isRunActive, pollWhileRunning } from "./runs";

import { formWidgetClassName } from "../forms/TextField";

/** The images filter that selects the same images the apply run will score.
 *
 * The runner resolves a target its own way, but every target kind is one
 * images filter here, so the count the user sees comes from the same catalogue
 * the run will pull from. Returns null when the target is not pickable yet.
 */
const countParams = (targetType: string, target: string): ImagesCountRetrieveParams | null => {
  if (!target) return null;
  if (targetType === "dataset") return { datasets: [target] };
  if (targetType === "tag") return { tags: [target] };
  if (targetType === "source") return { sources: [target] };
  if (targetType === "query") return { query: target };
  return null;
};

const TARGET_TYPES = [
  { value: "dataset", label: "Dataset" },
  { value: "query", label: "Saved query" },
  { value: "source", label: "Source" },
  { value: "tag", label: "Tag" },
];

/** Run this version over a target. Every image scored keeps its score.
 *
 * A target is one named set — a dataset version, saved query, source or tag —
 * because a run is one partition of one set on the runner's side. The target
 * scopes what gets SCORED, nothing more: which images the service pulls and
 * runs the model over. It does not gate what a score means — there
 * is still no threshold and no output dataset here, because the scores land on
 * the images and a cutoff stays a filter you apply afterwards.
 */
export const ClassifierApplyTab: React.FC<{ classifier: Classifier; onApplied: () => void }> = ({
  classifier,
  onApplied,
}) => {
  const queryClient = useQueryClient();
  const { data: trainings = [] } = useClassifiersTrainingsList(classifier.slug_version);
  const { data: runs = [] } = useClassifiersRunsList(classifier.slug_version, undefined, {
    query: { refetchInterval: pollWhileRunning },
  });
  const isTrained = trainings.some(training => training.status === "trained");
  const isRunning = runs.some(isRunActive);
  const [targetType, setTargetType] = useState("dataset");
  const [target, setTarget] = useState("");

  // The combobox reports every keystroke, so settle before counting: a partly
  // typed target is a different (usually empty) filter, not a target anyone
  // meant to size up.
  const [settledTarget, setSettledTarget] = useState(target);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettledTarget(target), 300);
    return () => window.clearTimeout(timer);
  }, [target]);

  const params = useMemo(() => countParams(targetType, settledTarget), [targetType, settledTarget]);
  const countQuery = useImagesCountRetrieve(params ?? {}, { query: { enabled: params !== null } });

  const applyMutation = useClassifiersApplyCreate({
    mutation: {
      onSuccess: run => {
        toast.success(
          run.dagster_run_url ? (
            <span>
              Apply started —{" "}
              <a href={run.dagster_run_url} target="_blank" rel="noreferrer" className="underline font-medium">
                watch it live in Dagster ↗
              </a>
            </span>
          ) : (
            "Apply started"
          ),
          { duration: 8000 }
        );
        queryClient.invalidateQueries({ queryKey: getClassifiersRunsListQueryKey(classifier.slug_version) });
        onApplied();
      },
      onError: () => toast.error("Could not start the apply run"),
    },
  });

  const apply = () => {
    if (!target) {
      toast.error("Name the target to apply to");
      return;
    }
    applyMutation.mutate({
      slugVersion: classifier.slug_version,
      data: { target_type: targetType as TargetTypeEnum, target_value: target },
    });
  };

  return (
    <div className="flex flex-col gap-4">
      {!isTrained && (
        <p className="text-sm opacity-60">Train this version before applying it, there is no model to score with.</p>
      )}
      <Card className="flex-col gap-3 p-4">
        <p className="text-sm">
          Scores the target&apos;s images and writes each result onto the image itself, as{" "}
          <code className="font-mono text-xs">classifications[&quot;{classifier.slug_version}&quot;]</code>.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex flex-col gap-1.5 sm:w-44">
            <label className="text-sm font-medium">Target</label>
            <select
              className={formWidgetClassName}
              value={targetType}
              onChange={e => {
                setTargetType(e.target.value);
                setTarget("");
              }}
            >
              {TARGET_TYPES.map(type => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5 flex-1">
            <label className="text-sm font-medium capitalize">{targetType}</label>
            <TargetCombobox targetType={targetType} value={target} onChange={setTarget} />
          </div>
        </div>
        <p className="text-sm">
          {params === null ? (
            <span className="opacity-60">Pick a {targetType} to see how many images it covers.</span>
          ) : countQuery.isPending ? (
            <span className="opacity-60">Counting images...</span>
          ) : countQuery.isError ? (
            <span className="opacity-60">Could not count this target&apos;s images.</span>
          ) : (
            <>
              <span className="font-medium">{(countQuery.data?.count ?? 0).toLocaleString()}</span> images match this
              target and would be scored.
            </>
          )}
        </p>
        <p className="text-xs opacity-60">
          The target only scopes what gets scored. There is still no threshold and no output dataset: every scored image
          ends up with a score for this version, so picking a cutoff, or comparing this classifier against another, is a
          filter on the images afterwards. Re-running only makes sense when the model changes or new images match the
          target.
        </p>
        <button
          type="button"
          className="btn btn-primary self-start"
          onClick={apply}
          disabled={!isTrained || isRunning || applyMutation.isPending}
        >
          {isRunning ? "Running..." : "Apply"}
        </button>
      </Card>
    </div>
  );
};
