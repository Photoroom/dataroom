import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeftIcon, LockClosedIcon } from "@heroicons/react/24/outline";
import { Classifier } from "../../api/client.schemas";
import { URLS } from "../../urls";

/** Context bar of the annotate workspace: which classifier, how far along, and
 * the way back. The labelling itself happens in the staging panel. */
export const ClassifierPanel: React.FC<{ classifier?: Classifier }> = ({ classifier }) => {
  if (!classifier) return null;

  return (
    <div className="flex items-center gap-2">
      <Link
        to={URLS.CLASSIFIER_DETAIL(classifier.slug, classifier.version)}
        className="flex items-center gap-1 text-xs opacity-60 hover:opacity-100"
        title="Back to the classifier"
      >
        <ArrowLeftIcon className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">{classifier.name}</span>
      </Link>
      <span className="text-[11px] tabular-nums opacity-50">
        +{classifier.counts.pos} / -{classifier.counts.neg}
      </span>
      {classifier.is_frozen && (
        <span className="text-[11px] flex items-center gap-1 opacity-60">
          <LockClosedIcon className="w-3.5 h-3.5" />
          locked (labels cannot be saved)
        </span>
      )}
    </div>
  );
};
