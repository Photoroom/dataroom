import React, { useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowPathIcon, ArrowTopRightOnSquareIcon, BeakerIcon, LockClosedIcon } from "@heroicons/react/24/outline";
import { getImagesListQueryKey, useClassifiersHoldoutCreate } from "../../api/client";
import { Classifier, ModeEnum } from "../../api/client.schemas";
import { Card } from "../common/Card";
import { DatasetPreviewGrid } from "./DatasetPreviewGrid";
import { extractApiError } from "../../api/errors";
import { URLS } from "../../urls";
import { MEASURABLE_PER_SIDE, heldOutShare } from "./validation";

// Offered as whole percentages: the API takes a fraction, but "20%" is how
// anyone actually thinks about a validation split, and a free number box
// invites values (0.2 vs 20) that mean wildly different things.
const PERCENTS = [10, 20, 30];

// A wide, shallow strip: enough to see WHICH images a sample took without
// turning the card into a second image browser, which Review is for. Ten
// across rather than sixteen because each thumbnail now carries two badges,
// its side and its score, and they need room to be read.
const PREVIEW_CELLS = 10;
const PREVIEW_COLUMNS = 10;
// Expanded, the same strip keeps its column count and just gets deeper, so
// the thumbnails stay the size they were rather than shrinking as it grows.
const EXPANDED_CELLS = 60;

// The images index only picks up the new membership on OpenSearch's own
// refresh interval (the denorm write does not refresh, see os_sync.py).
const OS_REFRESH_MS = 1500;

/** The validation set: the annotations training evaluates on but never
 * learns from.
 *
 * Its own card rather than a row inside each side, because it is one decision
 * across both sides — a set sampled from one side alone measures nothing — and
 * because the question it answers ("are these metrics honest?") is not the
 * question the side cards answer ("what does this learn from?").
 */
export const ClassifierValidationCard: React.FC<{ classifier: Classifier; onChanged: () => void }> = ({
  classifier,
  onChanged,
}) => {
  const [percent, setPercent] = useState(20);
  // A fresh sample moves images between trained-on and held-out, so the
  // stored scores no longer say what the badges imply: some come from a model
  // that trained on the image now being held out.
  const [resampled, setResampled] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const queryClient = useQueryClient();
  const { mutateAsync: holdout, isPending } = useClassifiersHoldoutCreate();
  const { val_pos: valPos, val_neg: valNeg, val_orphan: orphans } = classifier.counts;
  const total = valPos + valNeg;
  // The share as it stands now, not the one that was sampled: annotating after
  // a draw dilutes it, and nothing resamples on its own.
  const share = heldOutShare(classifier.counts);
  const thin = total > 0 && (valPos < MEASURABLE_PER_SIDE || valNeg < MEASURABLE_PER_SIDE);
  const shown = Math.min(total, isExpanded ? EXPANDED_CELLS : PREVIEW_CELLS);

  const draw = async () => {
    try {
      const result = await holdout({
        slugVersion: classifier.slug_version,
        data: { mode: ModeEnum.random, fraction: percent / 100 },
      });
      onChanged();
      setResampled(true);
      window.setTimeout(() => queryClient.invalidateQueries({ queryKey: getImagesListQueryKey() }), OS_REFRESH_MS);
      toast.success(`Validation set: ${result.val_pos} positive, ${result.val_neg} negative`);
    } catch (e) {
      toast.error(extractApiError(e, "Error sampling the validation set"));
    }
  };

  return (
    <Card className="flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <BeakerIcon className="w-4 h-4 opacity-50" />
        <span className="text-sm font-bold">Validation set</span>
        {total > 0 ? (
          <span className="text-xs opacity-50 tabular-nums">
            {valPos} positive · {valNeg} negative · {share}% of the examples
          </span>
        ) : (
          <span className="text-xs opacity-50">not set</span>
        )}
        <div className="flex-1" />
        {total > 0 && (
          <Link
            className="btn btn-sm btn-outline"
            // The annotate workspace rather than /images: there the tiles carry
            // this classifier's scores, and the held-out ones are the scores
            // worth looking at -- the model never trained on them.
            to={URLS.CLASSIFIER_ANNOTATE(
              classifier.slug,
              classifier.version,
              new URLSearchParams({ datasets: classifier.val_dataset })
            )}
            title="Review the validation set with the current model's scores"
          >
            <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" />
            Review
          </Link>
        )}
      </div>

      <p className="text-[11px] opacity-60 leading-relaxed">
        {total > 0 ? (
          <>The model never trains on these, so its scores here are a fair test. They keep their labels.</>
        ) : (
          <>
            Training needs one: the model is picked by its precision on these held-out examples. Press Sample to choose
            it now; otherwise Train holds out 20% of each side itself and keeps that set.
          </>
        )}
      </p>

      {thin && (
        <span className="text-[11px] px-2 py-1 rounded-md bg-amber-500/15 text-amber-800 dark:text-amber-300 self-start">
          Fewer than {MEASURABLE_PER_SIDE} on a side. A training still runs, but its metrics will move with which images
          the draw took rather than with the model — label more examples, then resample.
        </span>
      )}

      {/* Held out, but no longer an example of either side: what removing an
          image from a side dataset directly leaves behind (unlabelling it here
          takes it off this set too). Training and its metrics both skip these,
          so without saying it they are simply missing. */}
      {orphans > 0 && (
        <span className="text-[11px] px-2 py-1 rounded-md bg-amber-500/15 text-amber-800 dark:text-amber-300 self-start">
          {orphans} held-out image{orphans === 1 ? " is" : "s are"} no longer labelled on either side, so training and
          its metrics skip {orphans === 1 ? "it" : "them"}. Resample to clear {orphans === 1 ? "it" : "them"}.
        </span>
      )}

      {total > 0 && resampled && (
        <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-800 dark:text-amber-300 self-start">
          New sample. The scores below are from the previous training. Force retrain to regenerate them.
        </span>
      )}

      {/* The set itself, not just its size. A sample is a decision about
          particular images, and a pair of counts gives no way to notice it
          took the wrong ones. */}
      {total > 0 && (
        <div className="flex flex-col gap-1.5">
          <DatasetPreviewGrid
            datasets={[classifier.val_dataset]}
            cells={shown}
            columns={PREVIEW_COLUMNS}
            scoredClassifier={classifier.slug_version}
            posDatasets={[classifier.main_pos_dataset, ...(classifier.extra_pos_datasets ?? [])].filter(Boolean)}
            negDatasets={[classifier.main_neg_dataset, ...(classifier.extra_neg_datasets ?? [])].filter(Boolean)}
          />
          {total > PREVIEW_CELLS && (
            <div className="flex items-center gap-2 text-[11px] opacity-40">
              <span>
                First {shown} of {total}.
              </span>
              <button
                type="button"
                onClick={() => setIsExpanded(open => !open)}
                className="underline hover:opacity-100 cursor-pointer"
              >
                {isExpanded ? "Show fewer" : "Show more"}
              </button>
            </div>
          )}
        </div>
      )}

      {classifier.is_frozen ? (
        <span
          title={`v${classifier.version} is locked, so its validation set cannot change — which is what makes its metrics reproducible.`}
          className="flex items-center gap-1.5 text-[11px] opacity-60 self-start cursor-help"
        >
          <LockClosedIcon className="w-3.5 h-3.5 shrink-0" />
          Locked — unlock to change
        </span>
      ) : (
        <div className="flex items-center gap-2">
          <div className="flex gap-0.5 p-0.5 rounded-lg bg-black/5 dark:bg-white/5">
            {PERCENTS.map(value => (
              <button
                key={value}
                type="button"
                onClick={() => setPercent(value)}
                className={
                  value === percent
                    ? "px-2 py-1 text-xs font-medium rounded-md bg-white dark:bg-dark-100 shadow-sm cursor-pointer"
                    : "px-2 py-1 text-xs font-medium rounded-md opacity-50 hover:opacity-100 cursor-pointer"
                }
              >
                {value}%
              </button>
            ))}
          </div>
          <button type="button" className="btn btn-sm btn-outline" onClick={draw} disabled={isPending}>
            <ArrowPathIcon className="w-3.5 h-3.5" />
            {total > 0 ? "Resample" : "Sample"}
          </button>
          {/* Says what the button costs before it is pressed: resampling
              replaces the set, so an adjusted one is gone. */}
          {total > 0 && <span className="text-[11px] opacity-40">replaces the current set</span>}
        </div>
      )}
    </Card>
  );
};
