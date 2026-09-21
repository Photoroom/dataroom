import React, { useState } from "react";
import ReactDOM from "react-dom";
import {
  ArrowLongRightIcon,
  ArrowUturnLeftIcon,
  CubeTransparentIcon,
  CursorArrowRaysIcon,
  InformationCircleIcon,
  SparklesIcon,
  Squares2X2Icon,
  TagIcon,
} from "@heroicons/react/24/outline";
import Popup from "../common/Popup";

const Node: React.FC<{ icon: React.ReactNode; title: string; detail: string }> = ({ icon, title, detail }) => (
  <div className="flex-1 min-w-0 flex flex-col items-center text-center gap-1">
    <span className="w-9 h-9 rounded-lg bg-brand-500/10 text-brand-600 dark:text-brand-400 flex items-center justify-center">
      {icon}
    </span>
    <span className="text-xs font-medium">{title}</span>
    <span className="text-[11px] opacity-60 leading-snug">{detail}</span>
  </div>
);

const Arrow: React.FC = () => (
  <ArrowLongRightIcon className="w-6 h-6 shrink-0 opacity-30 mt-2 hidden sm:block" aria-hidden />
);

/** "How does this actually work?" The pipeline, drawn.
 *
 * The pieces only make sense in relation to each other, and a numbered list
 * hides the two things that matter: it is a loop, and locking cuts across it.
 */
export const HowClassifiersWork: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="opacity-50 hover:opacity-100 cursor-pointer"
        title="How classifiers work"
      >
        <InformationCircleIcon className="w-5 h-5" />
      </button>

      {isOpen &&
        ReactDOM.createPortal(
          <Popup onClose={() => setIsOpen(false)}>
            <h5 className="mb-1">How a classifier works</h5>
            <p className="text-xs opacity-60 mb-6">
              Dataroom stores the annotations, the versions and the runs. Dagster trains and scores, at{" "}
              <code className="font-mono">DAGSTER_GRAPHQL_URL</code>: a run reads the examples from this API and reports
              back.
            </p>

            <div className="flex items-start gap-2 sm:gap-3">
              <Node
                icon={<CubeTransparentIcon className="w-5 h-5" />}
                title="Embeddings"
                detail="Images carry a vector in the classifier's space"
              />
              <Arrow />

              {/* Two ways into the same step, not two steps. */}
              <div className="flex-[1.6] min-w-0 flex flex-col gap-1.5">
                <div className="text-xs font-medium text-center">Annotations</div>
                <div className="rounded-lg border border-dashed border-black/15 dark:border-white/15 p-2 flex flex-col gap-2">
                  <div className="flex items-start gap-2">
                    <Squares2X2Icon className="w-4 h-4 shrink-0 mt-0.5 opacity-60" />
                    <span className="text-[11px] leading-snug">
                      Add existing <code className="font-mono">single_image</code> datasets as positive or negative
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <CursorArrowRaysIcon className="w-4 h-4 shrink-0 mt-0.5 opacity-60" />
                    <span className="text-[11px] leading-snug">
                      Or label images into the classifier&apos;s own datasets
                    </span>
                  </div>
                </div>
              </div>

              <Arrow />
              <Node
                icon={<SparklesIcon className="w-5 h-5" />}
                title="Train"
                detail="Dagster trains on the examples, minus the validation set"
              />
              <Arrow />
              <Node
                icon={<TagIcon className="w-5 h-5" />}
                title="Apply"
                detail="Dagster scores the images you target with a trained model"
              />
            </div>

            <div className="flex items-center gap-2 text-[11px] opacity-60 mt-4 mb-6 justify-center">
              <ArrowUturnLeftIcon className="w-4 h-4" />
              <span>The images it scored least confidently are the best ones to label next.</span>
            </div>

            <dl className="flex flex-col gap-3 border-t border-black/10 dark:border-white/10 pt-4">
              <div>
                <dt className="text-xs font-medium">Main and additional datasets</dt>
                <dd className="text-[11px] opacity-70 mt-0.5">
                  Each side owns one internal <code className="font-mono">single_image</code> dataset, hidden from{" "}
                  <code className="font-mono">/api/datasets/</code>, which is where labelling writes. Putting an image
                  on one side takes it off the other in the same call, so nothing is annotated both ways. Additional
                  datasets are ordinary ones, referenced and never written to.
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium">Validation set</dt>
                <dd className="text-[11px] opacity-70 mt-0.5">
                  Examples kept back from training. They stay positive or negative as labelled, and being held out is a
                  mark on top of that. Metrics are measured on them, so re-drawing the set is worth another training
                  even when no side&apos;s total changed.
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium">Trainings</dt>
                <dd className="text-[11px] opacity-70 mt-0.5">
                  Every run leaves a record on the version: how many examples it learned from, the model it produced and
                  the metrics it scored. A version can hold as many as you like, and applying uses the latest unless you
                  pick another.
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium">Scores land on the image documents</dt>
                <dd className="text-[11px] opacity-70 mt-0.5">
                  Apply writes{" "}
                  <code className="font-mono">classifications[&quot;&lt;slug&gt;/&lt;version&gt;&quot;] = score</code>{" "}
                  on every image it scores. The threshold stays a search filter you can move without scoring again, and
                  an image carries a score per classifier applied to it.
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium">Locking and versions</dt>
                <dd className="text-[11px] opacity-70 mt-0.5">
                  Locking freezes the classifier and every dataset it owns, validation set included, pinning what the
                  version was trained and measured on. <code className="font-mono">new-version</code> copies those into
                  fresh versions and carries on there.
                </dd>
              </div>
            </dl>
          </Popup>,
          document.body
        )}
    </>
  );
};
