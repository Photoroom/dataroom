import React, { useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  ArrowTopRightOnSquareIcon,
  LockClosedIcon,
  PencilSquareIcon,
  PlusIcon,
  Squares2X2Icon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { twMerge } from "tailwind-merge";
import { useQueryClient } from "@tanstack/react-query";
import {
  getClassifiersRunsListQueryKey,
  useClassifiersApplyCreate,
  useClassifiersPartialUpdate,
  useClassifiersRunsList,
  useClassifiersTrainingsList,
} from "../../api/client";
import { Classifier, TargetTypeEnum } from "../../api/client.schemas";
import { Card } from "../common/Card";
import { DatasetCombobox } from "./DatasetCombobox";
import { DatasetPreviewGrid } from "./DatasetPreviewGrid";
import { ClassifierValidationCard } from "./ClassifierValidationCard";
import { isRunActive, pollWhileRunning } from "./runs";
import { extractApiError } from "../../api/errors";
import { URLS, datasetUrl } from "../../urls";

// An expanded side shows a wide, shallow grid: enough to judge what is in the
// set at a glance, not a second image browser. That is what the review link is for.
const EXPANDED_CELLS = 24;
const EXPANDED_COLUMNS = 8;

/** Every dataset the classifier learns from, both sides together. */
const allDatasetsOf = (classifier: Classifier) =>
  [
    classifier.main_pos_dataset,
    ...(classifier.extra_pos_datasets ?? []),
    classifier.main_neg_dataset,
    ...(classifier.extra_neg_datasets ?? []),
  ].filter(Boolean);

/** The workspace, with a filter already applied.
 *
 * Every link on this tab lands in the same place, so what separates them is
 * the filter, not the destination: what is already labelled on one side, what
 * is not labelled at all, a band of scores. A locked version cannot be
 * labelled, so it goes to the plain images view instead.
 */
const workspaceUrl = (classifier: Classifier, params: URLSearchParams) => {
  if (classifier.is_frozen) return URLS.IMAGE_LIST(params);
  return `${URLS.CLASSIFIER_ANNOTATE(classifier.slug, classifier.version)}?${params}`;
};

/** What is already on one side. */
const reviewUrl = (classifier: Classifier, datasets: string[]) =>
  workspaceUrl(classifier, new URLSearchParams({ datasets: datasets.join(",") }));

/** What neither side holds yet: the labelling queue.
 *
 * Opening the workspace unfiltered is how you end up scrolling past decisions
 * you already made, mixed in with the ones you have not. Excluding both sides'
 * datasets leaves only images that are still a question.
 */
const unlabelledUrl = (classifier: Classifier) => {
  const datasets = allDatasetsOf(classifier);
  if (datasets.length === 0) return workspaceUrl(classifier, new URLSearchParams());
  return workspaceUrl(classifier, new URLSearchParams({ datasets__ne: datasets.join(",") }));
};

/** A band of this version's scores (from its last apply), e.g.
 * ("gte:0.4", "lte:0.6"). */
const scoreBandUrl = (classifier: Classifier, ...constraints: string[]) =>
  workspaceUrl(
    classifier,
    new URLSearchParams({
      classifications: constraints.map(constraint => `${classifier.slug_version}__${constraint}`).join(","),
    })
  );

const SideSection: React.FC<{
  side: "positive" | "negative";
  classifier: Classifier;
  main: string;
  mainCount: number;
  extras: string[];
  extraCount: number;
  onChanged: () => void;
}> = ({ side, classifier, main, mainCount, extras, extraCount, onChanged }) => {
  const [isAdding, setIsAdding] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [candidate, setCandidate] = useState("");
  const allDatasets = [main, ...extras].filter(Boolean);
  const { mutateAsync: update, isPending } = useClassifiersPartialUpdate();
  const field = side === "positive" ? "extra_pos_datasets" : "extra_neg_datasets";
  const accent = side === "positive" ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400";

  const save = async (next: string[]) => {
    try {
      await update({ slugVersion: classifier.slug_version, data: { [field]: next } });
      onChanged();
      setCandidate("");
      setIsAdding(false);
    } catch (e) {
      toast.error(extractApiError(e, "Error changing the additional datasets"));
    }
  };

  return (
    <Card className="flex-col gap-3 p-4 flex-1">
      <div className="flex items-center gap-2">
        <span className={`text-sm font-bold capitalize ${accent}`}>{side}</span>
        <span className="text-xs opacity-50 tabular-nums">{mainCount + extraCount} images</span>
        <div className="flex-1" />
        {/* Icon only: showing the thumbnails is a glance, not an action worth a
            labelled button competing with the review link. */}
        <button
          type="button"
          onClick={() => setIsExpanded(open => !open)}
          disabled={allDatasets.length === 0}
          title={isExpanded ? "Hide the annotations" : "Show the annotations on this side"}
          className={twMerge(
            "p-1 rounded cursor-pointer transition-colors",
            isExpanded
              ? "bg-black/10 dark:bg-white/10 opacity-100"
              : "opacity-40 hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/5",
            allDatasets.length === 0 && "opacity-20 cursor-not-allowed hover:bg-transparent"
          )}
        >
          <Squares2X2Icon className="w-4 h-4" />
        </button>
        {/* One link, and its label says what the filter is: these are the
            images already on this side, not a way into the whole catalogue. */}
        <Link
          className="btn btn-sm btn-outline"
          to={reviewUrl(classifier, allDatasets)}
          title="Open every image already annotated on this side"
        >
          <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" />
          Review {side}s
        </Link>
      </div>

      {/* Expanded, this is the whole side at once — main and additional sets
          together, which is how the classifier actually sees them. The rows
          below stay the place to see WHERE those images come from. */}
      {isExpanded && (
        <div className="flex flex-col gap-1.5">
          <DatasetPreviewGrid
            datasets={allDatasets}
            cells={EXPANDED_CELLS}
            columns={EXPANDED_COLUMNS}
            scoredClassifier={classifier.slug_version}
          />
          {mainCount + extraCount > EXPANDED_CELLS && (
            <span className="text-[11px] opacity-40">
              First {EXPANDED_CELLS} of {mainCount + extraCount}. Review {side}s to see the rest.
            </span>
          )}
        </div>
      )}

      {/* The main set: belongs to this classifier, and where labelling writes. */}
      <div className="flex gap-3 rounded-lg border border-black/10 dark:border-white/10 p-2.5">
        <DatasetPreviewGrid datasets={main ? [main] : []} className="w-24 shrink-0" />
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium">Main dataset</span>
            <span className="text-xs tabular-nums opacity-60">{mainCount}</span>
          </div>
          <div className="font-mono text-[11px] opacity-60 truncate">{main || "-"}</div>
          {/* No button here. Labelling is not a per-side act (one click in the
              workspace cycles positive, negative, neither), so the way in is a
              single action at the top of the tab. This row says where the
              labels land, which is what it is actually good for. */}
          <div className="text-[11px] opacity-40">Where labelling on this side writes.</div>
        </div>
      </div>

      {/* Datasets curated elsewhere, added alongside the main one. */}
      <div className="flex flex-col gap-1.5">
        <div className="text-xs font-medium opacity-60">Additional datasets</div>
        {extras.length === 0 && (
          <p className="text-[11px] opacity-40">None. Add one to reuse annotations from elsewhere.</p>
        )}
        {extras.map(slugVersion => (
          <div key={slugVersion} className="flex items-center gap-2.5 text-xs">
            <DatasetPreviewGrid datasets={[slugVersion]} className="w-12 shrink-0" />
            <Link to={datasetUrl(slugVersion)} className="font-mono underline hover:opacity-80 truncate">
              {slugVersion}
            </Link>
            <div className="flex-1" />
            {!classifier.is_frozen && (
              <button
                type="button"
                className="opacity-50 hover:opacity-100 cursor-pointer"
                title="Remove this dataset from the classifier"
                onClick={() => save(extras.filter(existing => existing !== slugVersion))}
                disabled={isPending}
              >
                <XMarkIcon className="w-4 h-4" />
              </button>
            )}
          </div>
        ))}

        {!classifier.is_frozen &&
          (isAdding ? (
            <div className="flex flex-col gap-2 mt-1">
              <DatasetCombobox value={candidate} onChange={setCandidate} />
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  disabled={!candidate || isPending}
                  onClick={() => save([...extras, candidate])}
                >
                  Add
                </button>
                <button type="button" className="btn btn-sm btn-outline" onClick={() => setIsAdding(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className="btn btn-sm btn-outline self-start mt-1" onClick={() => setIsAdding(true)}>
              <PlusIcon className="w-3.5 h-3.5" />
              Add dataset
            </button>
          ))}
      </div>
    </Card>
  );
};

/** The three bands of this version's scores worth going back to.
 *
 * Uncertain is the active-learning queue (the model's least confident calls,
 * both sides of the threshold); low and high are the confident ends, for
 * spotting misses and spot-checking precision. The dots carry the same colours
 * the annotation badges do, so a band reads as the side it is about before the
 * words are read: rose for what the model calls negative, emerald for positive,
 * amber for the ones it cannot call.
 */
const BANDS = [
  {
    key: "uncertain",
    range: "0.4–0.6",
    dot: "bg-amber-500",
    constraints: ["gte:0.4", "lte:0.6"],
    title:
      "Images scored 0.4–0.6 — the model's least confident calls; labelling these improves the next training the most",
  },
  {
    key: "low",
    range: "≤0.4",
    dot: "bg-rose-500",
    constraints: ["lte:0.4"],
    title: "Images scored ≤ 0.4 — confident negatives; scan for positives the model is missing",
  },
  {
    key: "high",
    range: "≥0.6",
    dot: "bg-emerald-500",
    constraints: ["gte:0.6"],
    title: "Images scored ≥ 0.6 — confident positives; spot-check that they really belong",
  },
];

/** Where to find more examples.
 *
 * Everything here opens the same workspace and differs only in the filter, so
 * they read as places to draw from: images not yet judged, then the score
 * bands once a version has been applied. No link to the unfiltered catalogue:
 * every filter here is one chip the workspace shows and can drop, so getting
 * back to everything is already a click away once you are there.
 *
 * Deliberately no counts. The set of unjudged images is the catalogue minus a
 * few hundred, and a number next to a button turns it into a backlog with an
 * end. The classifier is done when it scores well, not when every image has
 * been looked at. Sizing the corpus is a job for the images view.
 */
const StartRow: React.FC<{ classifier: Classifier }> = ({ classifier }) => (
  <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
    {classifier.is_frozen ? (
      <span
        title={`v${classifier.version} is locked, so its annotations cannot change. Unlock it to label, or create v${classifier.version + 1} to carry on from it.`}
        className="flex items-center gap-1.5 opacity-60 cursor-help"
      >
        <LockClosedIcon className="w-3.5 h-3.5 shrink-0" />
        Locked — unlock to label
      </span>
    ) : (
      <Link
        className="btn btn-sm btn-primary"
        to={unlabelledUrl(classifier)}
        title="Open the workspace on images this classifier has not been given an answer for, so nothing you already judged is in the way"
      >
        <PencilSquareIcon className="w-3.5 h-3.5" />
        Label more examples
      </Link>
    )}
    {/* One segmented control, not three loose links: the bands are a single
        choice of where to look, and three underlined phrases next to a
        button read as three unrelated afterthoughts. */}
    <span className="opacity-50">Review scores</span>
    <div className="flex items-center rounded-lg border border-black/10 dark:border-white/10 overflow-hidden">
      {BANDS.map((band, index) => (
        <Link
          key={band.key}
          to={scoreBandUrl(classifier, ...band.constraints)}
          title={band.title}
          className={twMerge(
            "flex items-center gap-1.5 px-2.5 py-1 transition-colors",
            "hover:bg-black/5 dark:hover:bg-white/5",
            index > 0 && "border-l border-black/10 dark:border-white/10"
          )}
        >
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${band.dot}`} />
          <span className="capitalize">{band.key}</span>
          <span className="opacity-40 tabular-nums">{band.range}</span>
        </Link>
      ))}
    </div>
  </div>
);

/** The two sides, each with its main dataset and any additional ones. */

/** Where the scores on this tab come from, and a way to refresh them. */
const ScoresRow: React.FC<{ classifier: Classifier }> = ({ classifier }) => {
  const queryClient = useQueryClient();
  const { data: trainings = [] } = useClassifiersTrainingsList(classifier.slug_version);
  const { data: runs = [] } = useClassifiersRunsList(classifier.slug_version, undefined, {
    query: { refetchInterval: pollWhileRunning },
  });
  const model = trainings.find(training => training.status === "trained");
  // Re-scoring the annotations is an apply per dataset this version owns:
  // there is no "annotations" pseudo-target, a run is one set.
  const owned = [classifier.main_pos_dataset, classifier.main_neg_dataset, classifier.val_dataset].filter(
    (dataset): dataset is string => !!dataset
  );
  const rescores = runs.filter(run => run.target_type === "dataset" && owned.includes(run.target_value));
  const rescore = rescores[0];
  const running = rescores.some(isRunActive);
  const processed = rescores.filter(isRunActive).reduce((sum, run) => sum + run.processed, 0);
  const total = rescores.filter(isRunActive).reduce((sum, run) => sum + (run.total ?? 0), 0);

  const apply = useClassifiersApplyCreate({
    mutation: {
      onSuccess: () => {
        toast.success("Re-scoring the annotations");
        queryClient.invalidateQueries({ queryKey: getClassifiersRunsListQueryKey(classifier.slug_version) });
      },
      onError: e => toast.error(extractApiError(e, "Could not start re-scoring")),
    },
  });

  let info = "No model yet, train first";
  if (running) info = `Re-scoring ${processed}/${total || "?"}`;
  else if (rescore && rescore.status === "completed")
    info = `Scores from ${new Date(rescore.date_created).toLocaleString()}`;
  else if (model) info = `Scores from training on ${new Date(model.date_created).toLocaleString()}`;

  return (
    <div className="flex items-center gap-2 text-xs opacity-70">
      <span>{info}</span>
      <div className="flex-1" />
      <button
        type="button"
        className="btn btn-sm btn-outline"
        disabled={!model || running || apply.isPending}
        onClick={() =>
          owned.forEach(dataset =>
            apply.mutate({
              slugVersion: classifier.slug_version,
              data: { target_type: TargetTypeEnum.dataset, target_value: dataset },
            })
          )
        }
        title="Score every annotated image with the current model"
      >
        Re-score
      </button>
    </div>
  );
};

export const ClassifierAnnotationsTab: React.FC<{ classifier: Classifier; onChanged: () => void }> = ({
  classifier,
  onChanged,
}) => (
  <div className="flex flex-col gap-3">
    <StartRow classifier={classifier} />
    <ScoresRow classifier={classifier} />
    <div className="flex flex-col lg:flex-row gap-4">
      <SideSection
        side="positive"
        classifier={classifier}
        main={classifier.main_pos_dataset}
        mainCount={classifier.counts.main_pos}
        extras={classifier.extra_pos_datasets ?? []}
        extraCount={classifier.counts.extra_pos}
        onChanged={onChanged}
      />
      <SideSection
        side="negative"
        classifier={classifier}
        main={classifier.main_neg_dataset}
        mainCount={classifier.counts.main_neg}
        extras={classifier.extra_neg_datasets ?? []}
        extraCount={classifier.counts.extra_neg}
        onChanged={onChanged}
      />
    </div>
    <ClassifierValidationCard classifier={classifier} onChanged={onChanged} />
  </div>
);
