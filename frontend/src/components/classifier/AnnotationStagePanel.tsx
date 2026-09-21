import React, { useState } from "react";
import ReactDOM from "react-dom";
import { twMerge } from "tailwind-merge";
import toast from "react-hot-toast";
import { XMarkIcon } from "@heroicons/react/24/outline";
import { useClassifiersLabelCreate } from "../../api/client";
import { Classifier, SideEnum } from "../../api/client.schemas";
import { useImageListData } from "../../context/ImageListDataContext";
import { AnnotatedSide, StagedMark, useClassifierAnnotation } from "../../context/ClassifierAnnotationContext";
import { Image } from "../image/Image";
import { extractApiError } from "../../api/errors";
import { inBatches } from "./labelling";

const SECTIONS: Record<StagedMark, { heading: string; hint: string; text: string; tint: string; dim?: boolean }> = {
  positive: {
    heading: "+ positive",
    hint: "Click an image once.",
    text: "text-emerald-700 dark:text-emerald-400",
    tint: "bg-emerald-500/10",
  },
  negative: {
    heading: "− negative",
    hint: "Click an image twice.",
    text: "text-rose-700 dark:text-rose-400",
    tint: "bg-rose-500/10",
  },
  clear: {
    heading: "⊘ remove",
    hint: "Use the ⊘ on an image that is already annotated.",
    text: "text-neutral-600 dark:text-neutral-400",
    tint: "bg-black/5 dark:bg-white/5",
    dim: true,
  },
};

const Section: React.FC<{
  mark: StagedMark;
  imageIds: string[];
  imagesById: Map<string, ReturnType<typeof Object>>;
  onRemove: (imageId: string) => void;
}> = ({ mark, imageIds, imagesById, onRemove }) => {
  const section = SECTIONS[mark];
  return (
    <div className="flex flex-col gap-1.5">
      <div className={twMerge("flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide", section.text)}>
        <span>{section.heading}</span>
        <span className="tabular-nums opacity-60">{imageIds.length}</span>
      </div>
      <div className={twMerge("rounded-lg p-1.5 min-h-[3rem]", section.tint)}>
        {imageIds.length === 0 ? (
          <p className="text-[11px] opacity-40 p-1">{section.hint}</p>
        ) : (
          <div className="grid grid-cols-5 sm:grid-cols-4 gap-1.5">
            {imageIds.map(imageId => {
              const image = imagesById.get(imageId);
              return (
                <div key={imageId} className="relative group aspect-square">
                  {image ? (
                    <Image image={image} className={section.dim ? "opacity-50 grayscale" : undefined} />
                  ) : (
                    <div className="w-full h-full rounded-lg bg-black/10 dark:bg-white/10" />
                  )}
                  <button
                    type="button"
                    onClick={() => onRemove(imageId)}
                    className={twMerge(
                      "absolute top-0.5 right-0.5 p-0.5 rounded-full",
                      "bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                    )}
                    title="Unstage"
                  >
                    <XMarkIcon className="size-3" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

/** The annotate workspace's staging panel.
 *
 * Clicks stage labels rather than writing them, and this is where they collect:
 * a green section, a red one and a grey one for images leaving the classifier,
 * committed together with Add. Nothing is written until then, so a mis-click
 * costs one more click.
 */
export const AnnotationStagePanel: React.FC<{ classifier?: Classifier; onSaved: () => void }> = ({
  classifier,
  onSaved,
}) => {
  const { staged, setMark, clearStaged, markLocally } = useClassifierAnnotation();
  const unstage = (imageId: string) => setMark(imageId, null);
  const { images } = useImageListData();
  const { mutateAsync: labelImages } = useClassifiersLabelCreate();
  const [isBusy, setIsBusy] = useState(false);

  const total = staged.positive.length + staged.negative.length + staged.clear.length;
  const imagesById = new Map(images.map(image => [image.id, image]));

  const save = async () => {
    if (!classifier || total === 0) return;
    // One call per side, not one per dataset: the classifier owns both annotation
    // sets, so it can put an image on this side and take it off the other in
    // the same write. Labelling each dataset separately left an image that
    // changed its mind sitting in both. `none` is the same call with neither
    // side, which is how a saved annotation leaves the classifier.
    const targets: [string[], SideEnum, AnnotatedSide][] = [
      [staged.positive, SideEnum.positive, "positive"],
      [staged.negative, SideEnum.negative, "negative"],
      [staged.clear, SideEnum.none, null],
    ];
    const toastId = toast.loading(`Saving ${total} labels...`);
    setIsBusy(true);
    try {
      let done = 0;
      for (const [imageIds, apiSide, side] of targets) {
        if (!imageIds.length) continue;
        await inBatches(
          imageIds,
          batch => labelImages({ slugVersion: classifier.slug_version, data: { image_ids: batch, side: apiSide } }),
          saved => toast.loading(`Saving ${done + saved}/${total} labels...`, { id: toastId })
        );
        done += imageIds.length;
        markLocally(imageIds, side);
      }
      toast.success(`Saved ${done} labels`, { id: toastId });
      clearStaged();
      onSaved();
    } catch (e) {
      toast.error(extractApiError(e, "Error saving labels"), { id: toastId });
    } finally {
      setIsBusy(false);
    }
  };

  return ReactDOM.createPortal(
    <div
      className={twMerge(
        "fixed z-10 bottom-0 left-0 right-0 h-1/2",
        "md:left-auto md:top-14 md:bottom-0 md:h-auto md:w-drawer",
        "bg-white dark:bg-dark-100",
        "border-t md:border-t-0 md:border-l border-light-300 dark:border-dark-300",
        "shadow-xl flex flex-col rounded-t-xl md:rounded-t-none md:rounded-l-xl"
      )}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-light-200 dark:border-dark-300 shrink-0">
        <span className="text-sm font-medium">Staged labels ({total})</span>
        {total > 0 && (
          <button
            type="button"
            onClick={clearStaged}
            className="text-xs opacity-50 hover:opacity-100 cursor-pointer"
            disabled={isBusy}
          >
            Clear
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 p-3 flex flex-col gap-4">
        <Section mark="positive" imageIds={staged.positive} imagesById={imagesById} onRemove={unstage} />
        <Section mark="negative" imageIds={staged.negative} imagesById={imagesById} onRemove={unstage} />
        <Section mark="clear" imageIds={staged.clear} imagesById={imagesById} onRemove={unstage} />
        <p className="text-[11px] opacity-40">
          Click once for positive, twice for negative. The ⊘ on an image that is already annotated takes it off the
          classifier. Nothing is written until you press Save.
        </p>
      </div>

      <div className="px-4 py-3 border-t border-light-200 dark:border-dark-300 shrink-0">
        <button type="button" className="btn btn-primary w-full" onClick={save} disabled={isBusy || total === 0}>
          {isBusy ? "Saving..." : `Save ${total || ""} labels`}
        </button>
      </div>
    </div>,
    document.body
  );
};
