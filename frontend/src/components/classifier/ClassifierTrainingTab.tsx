import React from "react";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";
import { twMerge } from "tailwind-merge";
import {
  getClassifiersTrainingsListQueryKey,
  useClassifiersTrainCreate,
  useClassifiersTrainingsList,
} from "../../api/client";
import { Classifier, ClassifierTraining } from "../../api/client.schemas";
import { Card } from "../common/Card";
import { MEASURABLE_PER_SIDE } from "./validation";

/** One metric the service reported. Every name is prefixed `val_` and every
 * value was measured on the held-out set — there are no training-set metrics
 * here, on purpose: a model's score on what it learned from says nothing. */
const metric = (training: ClassifierTraining | undefined, name: string): number | undefined => {
  const value = training?.metrics?.[name];
  return typeof value === "number" ? value : undefined;
};

/** `val_auc` is what the old MLP trainer called AUROC. Read both, so a
 * training from before the query head still shows its number. */
const auroc = (training?: ClassifierTraining) => metric(training, "val_auroc") ?? metric(training, "val_auc");

/** Metrics arrive as full doubles (0.6324786324786326). Three decimals is more
 * than a few dozen held-out images can actually distinguish. */
const show = (value?: number) => (value === undefined ? "-" : value.toFixed(3));

const Metric: React.FC<{ label: string; value?: number; title?: string }> = ({ label, value, title }) => (
  <div className="flex flex-col" title={title}>
    <span className="text-lg font-bold tabular-nums">{show(value)}</span>
    <span className="text-[11px] opacity-60">{label}</span>
  </div>
);

/** One past training: what it was trained on, and what came out. */
const TrainingRow: React.FC<{ training: ClassifierTraining; isCurrent: boolean }> = ({ training, isCurrent }) => (
  <div className="flex items-center gap-3 py-2 border-b border-black/5 dark:border-white/5 last:border-0 text-xs">
    <span className="font-mono opacity-60 w-28 shrink-0 truncate" title={training.id}>
      {training.id.slice(0, 8)}
    </span>
    <span className="tabular-nums w-24 shrink-0">
      +{training.n_pos} / -{training.n_neg}
    </span>
    <span
      className="tabular-nums w-20 shrink-0"
      title={`${training.n_val} annotations were kept out of training and measured on`}
    >
      {training.n_val || "-"}
    </span>
    <span className="tabular-nums w-20 shrink-0" title="Average precision on the held-out set">
      {show(metric(training, "val_ap"))}
    </span>
    <span className="opacity-60 flex-1 truncate">{new Date(training.date_created).toLocaleString()}</span>
    {training.forced && <span className="opacity-50 shrink-0">forced</span>}
    {isCurrent && (
      <span className="px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 shrink-0">
        in use
      </span>
    )}
    {training.status === "training" && <span className="opacity-60 shrink-0">running</span>}
    {training.dagster_run_url && (
      <a
        href={training.dagster_run_url}
        target="_blank"
        rel="noreferrer"
        className="text-brand-600 dark:text-brand-400 hover:underline shrink-0"
        title="Open this run in the Dagster UI"
      >
        view live ↗
      </a>
    )}
    {training.status === "failed" && (
      <span className="text-red-600 dark:text-red-400 shrink-0" title={training.error}>
        failed
      </span>
    )}
  </div>
);

/** What the val_* numbers above were measured on.
 *
 * Without this the metrics read as "the accuracy", when they are the accuracy
 * on one particular handful of images — and on a handful, how many of them are
 * positive decides whether the numbers mean anything at all.
 */
const MeasuredOn: React.FC<{ training: ClassifierTraining }> = ({ training }) => {
  const total = metric(training, "val_n");
  const pos = metric(training, "val_n_pos");
  const neg = total !== undefined && pos !== undefined ? total - pos : undefined;
  const threshold = metric(training, "val_threshold_f1_best");

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] opacity-60">
        Measured on {total ?? training.n_val} held-out annotation{(total ?? training.n_val) === 1 ? "" : "s"}
        {pos !== undefined && neg !== undefined ? ` — ${pos} positive, ${neg} negative` : ""}. A version is locked when
        it trains, so every training of it measures the same images.
        {threshold !== undefined && ` Best F1 at scores of ${threshold.toFixed(3)} and up.`}
      </p>
      {pos !== undefined && pos < MEASURABLE_PER_SIDE && (
        <p className="text-[11px] px-2.5 py-1.5 rounded-md bg-amber-500/15 text-amber-800 dark:text-amber-300">
          Only {pos} held-out positive{pos === 1 ? "" : "s"}. Average precision and recall shift by a lot per image at
          this size, so read these as a hint rather than a measurement — label more positives in a new version to
          measure this properly.
        </p>
      )}
    </div>
  );
};

/** The checkpoint this version scores with, and every training that produced one. */
export const ClassifierTrainingTab: React.FC<{ classifier: Classifier }> = ({ classifier }) => {
  const queryClient = useQueryClient();
  const { data: trainings = [] } = useClassifiersTrainingsList(classifier.slug_version, undefined, {
    query: {
      // Poll while a training is running so `training -> trained | failed`
      // shows up without a manual refresh.
      refetchInterval: query =>
        (query.state.data ?? []).some(training => training.status === "training") ? 2000 : false,
    },
  });
  const checkpoint = trainings.find(training => training.status === "trained");
  const isRunning = trainings.some(training => training.status === "training");
  const hasDrifted =
    checkpoint && (checkpoint.n_pos !== classifier.counts.pos || checkpoint.n_neg !== classifier.counts.neg);
  // The runner picks the checkpoint by held-out precision, so Train needs a set
  // on both sides; without one it draws the default share and keeps it.
  const { val_pos: valPos, val_neg: valNeg } = classifier.counts;
  const hasValidationSet = valPos > 0 && valNeg > 0;
  const thinValidation = hasValidationSet && (valPos < MEASURABLE_PER_SIDE || valNeg < MEASURABLE_PER_SIDE);

  const train = useClassifiersTrainCreate({
    mutation: {
      onSuccess: training => {
        if (training.status !== "training") {
          toast.success("Already trained on these annotations. Use force to retrain");
        } else if (training.dagster_run_url) {
          // Hand over the run link right away, not only via the history row.
          toast.success(
            <span>
              Training started —{" "}
              <a href={training.dagster_run_url} target="_blank" rel="noreferrer" className="underline font-medium">
                watch it live in Dagster ↗
              </a>
            </span>,
            { duration: 8000 }
          );
        } else {
          toast.success("Training started");
        }
        queryClient.invalidateQueries({ queryKey: getClassifiersTrainingsListQueryKey(classifier.slug_version) });
      },
      onError: () => toast.error("Could not start the training"),
    },
  });
  const run = (force: boolean) => train.mutate({ slugVersion: classifier.slug_version, data: { force } });

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex-col gap-3 p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium">{checkpoint ? "Checkpoint in use" : "Not trained yet"}</span>
          {hasDrifted && (
            <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-800 dark:text-amber-300">
              annotations changed since: {checkpoint.n_pos}/{checkpoint.n_neg} then, {classifier.counts.pos}/
              {classifier.counts.neg} now
            </span>
          )}
        </div>
        <p className="text-xs opacity-60">
          Each training fits a small classification head on top of the frozen
          {classifier.embedding_space ? ` ${classifier.embedding_space}` : ""} backbone and saves the head as a
          checkpoint. Apply loads the checkpoint in use to score images.
        </p>

        {checkpoint && (
          <>
            <div className="text-xs tabular-nums">
              Trained on {checkpoint.n_pos} positive and {checkpoint.n_neg} negative annotations,{" "}
              {new Date(checkpoint.date_created).toLocaleString()}
            </div>
            {/* What the service actually reports, led by the one it picks the
                checkpoint by. Precision and recall AT 0.5 are deliberately not
                here: nothing says a useful cutoff sits at 0.5, and on an
                unbalanced set they read as zero while the model ranks fine. */}
            <div className="flex gap-8">
              <Metric
                label="avg precision"
                value={metric(checkpoint, "val_ap")}
                title="Area under the precision-recall curve. The training keeps the checkpoint that scores highest on this."
              />
              <Metric
                label="AUROC"
                value={auroc(checkpoint)}
                title="How well the checkpoint ranks positives above negatives."
              />
              <Metric
                label="best F1"
                value={metric(checkpoint, "val_f1_best")}
                title="The best F1 any single cutoff reaches, and the line below says which cutoff that is."
              />
              <Metric
                label="recall @ 90%"
                value={metric(checkpoint, "val_recall_at_p90")}
                title="How many of the positives you can catch while 9 in 10 of what you catch is right."
              />
            </div>
            <MeasuredOn training={checkpoint} />
            <div className="text-[11px] opacity-60 font-mono break-all">checkpoint {checkpoint.model_id}</div>
          </>
        )}

        {!hasValidationSet && (
          <p className="text-xs px-2.5 py-1.5 rounded-md bg-amber-500/15 text-amber-800 dark:text-amber-300">
            No validation set yet. Train will hold out 20% of each side and keep that set for every later retrain. To
            choose it yourself, sample one on the Annotations tab first.
          </p>
        )}
        {thinValidation && (
          <p className="text-xs px-2.5 py-1.5 rounded-md bg-amber-500/15 text-amber-800 dark:text-amber-300">
            The validation set holds {valPos} positive and {valNeg} negative. Training runs, but fewer than{" "}
            {MEASURABLE_PER_SIDE} on a side cannot measure anything: expect metrics that move with the draw rather than
            with the model.
          </p>
        )}
        <p className="text-xs opacity-60">
          Retrain on unchanged annotations reuses the checkpoint in use. Force retrain always makes a new checkpoint,
          for example after the training code changed.
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => run(false)}
            disabled={isRunning || train.isPending}
          >
            {checkpoint ? "Retrain" : "Train"}
          </button>
          <button
            type="button"
            className="btn btn-outline"
            onClick={() => run(true)}
            disabled={isRunning || train.isPending}
          >
            Force retrain
          </button>
        </div>
      </Card>

      <Card className="flex-col gap-1 p-4">
        <span className="text-sm font-medium mb-1">Training history</span>
        {trainings.length === 0 ? (
          <p className="text-xs opacity-50">Nothing yet.</p>
        ) : (
          <>
            <div
              className={twMerge(
                "flex items-center gap-3 pb-1 text-[11px] uppercase tracking-wide opacity-40",
                "border-b border-black/10 dark:border-white/10"
              )}
            >
              <span className="w-28 shrink-0">run</span>
              <span className="w-24 shrink-0">annotations</span>
              <span className="w-20 shrink-0">held out</span>
              <span className="w-20 shrink-0">avg prec</span>
              <span className="flex-1">started</span>
            </div>
            {trainings.map(training => (
              <TrainingRow key={training.id} training={training} isCurrent={training.id === checkpoint?.id} />
            ))}
          </>
        )}
      </Card>
    </div>
  );
};
