import React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { twMerge } from "tailwind-merge";
import { Dataset } from "../../api/client.schemas";
import { useDatasetsGroupsRetrieve } from "../../api/client";
import { formatNumber } from "../../utils/formatNumber";
import { URLS } from "../../urls";

// the thumbnail is always a fixed 2x2 frame of member-group covers
const MAX_COLLAGE_TILES = 4;

interface DatasetCardProps {
  dataset: Dataset;
}

export const DatasetCard: React.FC<DatasetCardProps> = function ({ dataset }) {
  // Collage covers come from the groups sub-resource, one small page per card
  // (react-query caches per slug_version). The frame is always 2x2: cells
  // pulse while loading and stay grey where the dataset has no cover to show,
  // so the grid doesn't reflow as pages arrive.
  const { data: groupsData, isPending } = useDatasetsGroupsRetrieve(
    dataset.slug_version,
    { page_size: MAX_COLLAGE_TILES },
    { query: { enabled: dataset.group_count > 0 } }
  );
  const collageThumbs = (groupsData?.results ?? []).map(g => g.cover_thumbnail).filter((t): t is string => Boolean(t));
  const isLoadingThumbs = dataset.group_count > 0 && isPending;

  // open the drawer via ?dataset=, list stays behind (like GroupCard)
  const [searchParams] = useSearchParams();
  const drawerParams = new URLSearchParams(searchParams);
  drawerParams.set("dataset", dataset.slug_version);

  return (
    <Link
      to={URLS.DATASET_LIST(drawerParams)}
      title={dataset.name}
      className="group block w-full rounded-xl overflow-hidden bg-white dark:bg-dark-100 ring-1 ring-black/15 dark:ring-white/15 hover:ring-brand-400/60 shadow-sm hover:shadow-md transition-[box-shadow,color]"
    >
      {/* The card surface is the only backdrop: it shows as an even mat around
          and between the cells, so there are no competing grey/white zones. */}
      <div className="relative w-full aspect-square overflow-hidden p-1.5">
        {dataset.group_count === 0 ? (
          <div className="flex items-center justify-center w-full h-full rounded-md bg-black/6 dark:bg-white/6 text-xs opacity-40">
            No images
          </div>
        ) : (
          <div className="grid grid-cols-2 grid-rows-2 h-full w-full gap-1.5">
            {Array.from({ length: MAX_COLLAGE_TILES }, (_, i) => {
              const thumb = collageThumbs[i];
              return (
                <div
                  key={i}
                  className={twMerge(
                    "overflow-hidden rounded-md bg-black/6 dark:bg-white/6",
                    isLoadingThumbs && "animate-pulse"
                  )}
                >
                  {thumb && (
                    <img
                      src={thumb}
                      alt=""
                      loading="lazy"
                      className="w-full h-full object-cover"
                      // a cover whose thumbnail 404s reads as "no cover": stay grey
                      onError={e => (e.currentTarget.style.display = "none")}
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
      {/* Info block: full-width bold name line, then type/frozen chips + count.
          Type lives here (not overlaid on the collage) so the covers stay clean
          and the metadata reads at a glance. */}
      <div className="flex flex-col gap-1 px-2.5 pb-2.5 pt-1">
        <span className="truncate text-sm font-bold" title={dataset.name}>
          {dataset.name}
          <span className="text-xs font-normal opacity-40"> v{dataset.version}</span>
        </span>
        <span className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1 min-w-0">
            <span className="truncate text-[10px] font-medium uppercase px-1.5 py-0.5 rounded-full bg-brand-100 text-brand-700 dark:bg-brand-900 dark:text-brand-300">
              {dataset.type}
            </span>
            {dataset.is_frozen && (
              <span className="shrink-0 text-[10px] font-medium uppercase px-1.5 py-0.5 rounded-full bg-cyan-400/40 dark:bg-cyan-600/40">
                frozen
              </span>
            )}
          </span>
          <span className="shrink-0 text-xs tabular-nums opacity-60">
            {formatNumber(dataset.group_count, { decimals: 0 })} groups
          </span>
        </span>
      </div>
    </Link>
  );
};
