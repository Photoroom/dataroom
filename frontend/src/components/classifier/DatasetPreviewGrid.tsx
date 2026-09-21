import React from "react";
import { twMerge } from "tailwind-merge";
import { useImagesList } from "../../api/client";
import { ScoreBadge } from "./ScoreBadge";
import { AnnotationBadge } from "./AnnotationBadge";
import { AnnotatedSide } from "../../context/ClassifierAnnotationContext";

const CELLS = 9;
const COLUMNS = 3;

/** A small peek at what is inside a set of datasets.
 *
 * One request for a handful of thumbnails, so a card can show what it holds
 * instead of just a number. Empty slots keep the square shape rather than
 * collapsing, so rows of these stay aligned. `cells`/`columns` trade the square
 * 3x3 block for a single strip where the space is a column, not a card.
 *
 * `scoredClassifier` puts that classifier's score on each thumbnail. The field
 * is opt-in server-side, so it is only requested when it will be shown.
 *
 * `posDatasets`/`negDatasets` mark which side each image is annotated on. On
 * the validation set that is the whole point: a score means nothing until you
 * know whether the image was meant to be a positive or a negative.
 */
export const DatasetPreviewGrid: React.FC<{
  datasets: string[];
  className?: string;
  cells?: number;
  columns?: number;
  scoredClassifier?: string;
  posDatasets?: string[];
  negDatasets?: string[];
}> = ({ datasets, className, cells = CELLS, columns = COLUMNS, scoredClassifier, posDatasets, negDatasets }) => {
  const showsSide = Boolean(posDatasets?.length || negDatasets?.length);
  const fields = ["thumbnail", "image"];
  if (scoredClassifier) fields.push("classifications");
  if (showsSide) fields.push("datasets");
  const { data, isLoading } = useImagesList(
    { datasets, page_size: cells, include_fields: fields.join(",") },
    { query: { enabled: datasets.length > 0 } }
  );

  // Same rule the annotate workspace badges by: the side an image is on is the
  // side dataset it is still a member of, held out or not.
  const sideOf = (imageDatasets: string[] | null | undefined): AnnotatedSide => {
    const inSet = imageDatasets ?? [];
    if (inSet.some(slugVersion => posDatasets?.includes(slugVersion))) return "positive";
    if (inSet.some(slugVersion => negDatasets?.includes(slugVersion))) return "negative";
    return null;
  };

  const rank = (side: AnnotatedSide) => (side === "positive" ? 0 : side === "negative" ? 1 : 2);
  const images = [...(data?.results ?? [])];
  if (showsSide) images.sort((a, b) => rank(sideOf(a.datasets)) - rank(sideOf(b.datasets)));

  return (
    <div
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      className={twMerge("grid gap-0.5 w-full", className)}
    >
      {Array.from({ length: cells }).map((_, index) => {
        const image = images[index];
        return (
          <div
            key={image?.id ?? `empty-${index}`}
            className={twMerge(
              "aspect-square rounded-[3px] overflow-hidden",
              "bg-black/5 dark:bg-white/5",
              isLoading && "animate-pulse"
            )}
          >
            {image && (
              <div className="relative w-full h-full">
                <img
                  src={image.thumbnail || image.image}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  className="w-full h-full object-cover"
                />
                {showsSide && (
                  <span className="absolute top-0.5 left-0.5 scale-50 origin-top-left">
                    <AnnotationBadge side={sideOf(image.datasets)} />
                  </span>
                )}
                {scoredClassifier && image.classifications?.[scoredClassifier] !== undefined && (
                  <span className="absolute bottom-0.5 right-0.5 origin-bottom-right">
                    <ScoreBadge score={image.classifications[scoredClassifier]} />
                  </span>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
