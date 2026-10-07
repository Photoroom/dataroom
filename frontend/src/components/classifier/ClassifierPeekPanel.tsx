import React from "react";
import { Link } from "react-router-dom";
import { twMerge } from "tailwind-merge";
import { ArrowTopRightOnSquareIcon, PencilSquareIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { Classifier } from "../../api/client.schemas";
import { TextToParagraphs } from "../common/TextToParagraphs";
import { DatasetPreviewGrid } from "./DatasetPreviewGrid";
import { URLS, browseUrl, datasetUrl } from "../../urls";

// A strip, not a block: enough thumbnails to recognise what is in a side,
// few enough that both sides and their dataset lists fit without scrolling.
const STRIP_CELLS = 4;

/** One side of the classifier, said once: how many, what it looks like, and
 * which datasets it comes from. The main dataset leads, extras are indented
 * under it. */
const SidePreview: React.FC<{
  side: "positive" | "negative";
  classifier: Classifier;
  main: string;
  extras: string[];
  count: number;
}> = ({ side, classifier, main, extras, count }) => {
  const datasets = [main, ...extras].filter(Boolean);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2 text-xs">
        <span
          className={twMerge(
            "font-medium capitalize",
            side === "positive" ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"
          )}
        >
          {side}
        </span>
        <span className="tabular-nums opacity-50">{count.toLocaleString()}</span>
        <div className="flex-1" />
        {datasets.length > 0 && (
          <Link to={browseUrl(classifier, datasets)} className="text-[11px] opacity-50 hover:opacity-100">
            browse
          </Link>
        )}
      </div>
      <DatasetPreviewGrid datasets={datasets} cells={STRIP_CELLS} columns={STRIP_CELLS} />
      <div className="flex flex-col gap-0.5">
        {main && (
          <Link to={datasetUrl(main)} className="font-mono text-[11px] opacity-70 hover:opacity-100 truncate">
            {main}
          </Link>
        )}
        {extras.map(slugVersion => (
          <Link
            key={slugVersion}
            to={datasetUrl(slugVersion)}
            className="font-mono text-[11px] opacity-50 hover:opacity-100 truncate pl-3"
          >
            {slugVersion}
          </Link>
        ))}
      </div>
    </div>
  );
};

/** A look at a classifier without leaving the list.
 *
 * A classifier has no cover: the pictures that mean something are its two
 * annotation sides, so the panel leads with the name and then says each side
 * exactly once — count, a strip of thumbnails, and the datasets behind it.
 */
export const ClassifierPeekPanel: React.FC<{ classifier: Classifier; onClose: () => void }> = ({
  classifier,
  onClose,
}) => {
  const counts = classifier.counts;
  const detailUrl = URLS.CLASSIFIER_DETAIL(classifier.slug, classifier.version);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto min-h-0 p-4 flex flex-col gap-4">
        {/* Title + meta */}
        <div className="flex flex-col gap-1 min-w-0">
          <div className="flex items-start gap-2">
            <Link to={detailUrl} className="min-w-0 flex-1 hover:opacity-70 transition-opacity">
              <h4 className="text-lg font-bold leading-tight break-words">{classifier.name}</h4>
            </Link>
            <Link
              to={detailUrl}
              title="Open classifier"
              className="p-1 opacity-40 hover:opacity-100 transition-opacity shrink-0"
            >
              <ArrowTopRightOnSquareIcon className="size-4" />
            </Link>
            <button
              type="button"
              onClick={onClose}
              title="Close"
              className="p-1 opacity-40 hover:opacity-100 transition-opacity shrink-0 cursor-pointer"
            >
              <XMarkIcon className="size-4" />
            </button>
          </div>
          <span className="text-xs font-mono opacity-40">{classifier.slug_version}</span>
          <p className="text-xs opacity-40">
            {classifier.author?.email && <>by {classifier.author.email}, </>}
            updated {new Date(classifier.date_updated).toLocaleDateString()}
          </p>
          <div className="flex items-center gap-1.5 flex-wrap mt-1">
            {classifier.embedding_space && (
              <span className="text-[10px] font-medium uppercase px-2 py-0.5 rounded-full bg-brand-100 text-brand-700 dark:bg-brand-900 dark:text-brand-300">
                {classifier.embedding_space}
              </span>
            )}
            {classifier.is_frozen && (
              <span className="text-[10px] font-medium uppercase px-2 py-0.5 rounded-full bg-cyan-400/40 dark:bg-cyan-600/40">
                locked
              </span>
            )}
          </div>
        </div>

        {classifier.description && <TextToParagraphs text={classifier.description} className="text-sm opacity-70" />}

        {/* What this version is for, as opposed to what the classifier is. */}
        {classifier.version_note && (
          <p className="text-sm border-l-2 border-black/10 dark:border-white/10 pl-3">
            <span className="opacity-50 tabular-nums">v{classifier.version}: </span>
            <span className="opacity-80">{classifier.version_note}</span>
          </p>
        )}

        <SidePreview
          side="positive"
          classifier={classifier}
          main={classifier.main_pos_dataset}
          extras={classifier.extra_pos_datasets ?? []}
          count={counts.pos}
        />
        <SidePreview
          side="negative"
          classifier={classifier}
          main={classifier.main_neg_dataset}
          extras={classifier.extra_neg_datasets ?? []}
          count={counts.neg}
        />
      </div>

      <div className="flex gap-2 px-4 py-3 border-t border-light-200 dark:border-dark-300 shrink-0">
        <Link className="btn btn-primary flex-1" to={detailUrl}>
          Open
        </Link>
        {!classifier.is_frozen && (
          <Link className="btn btn-outline flex-1" to={URLS.CLASSIFIER_ANNOTATE(classifier.slug, classifier.version)}>
            <PencilSquareIcon className="w-4 h-4" />
            Annotate
          </Link>
        )}
      </div>
    </div>
  );
};
