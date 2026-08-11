import React, { useState } from "react";
import {
  ArrowLeftIcon,
  ArrowTopRightOnSquareIcon,
  LockClosedIcon,
  LockOpenIcon,
  TrashIcon,
  PhotoIcon,
  PlusIcon,
} from "@heroicons/react/24/outline";
import { keepPreviousData } from "@tanstack/react-query";
import { formatNumber } from "../../utils/formatNumber";
import {
  useDatasetsList,
  useDatasetsGroupsRetrieve,
  useDatasetsFreezeCreate,
  useDatasetsUnfreezeCreate,
  useDatasetsDestroy,
  useDatasetsPartialUpdate,
  useGroupTypesRetrieve,
} from "../../api/client";
import { TextToParagraphs } from "../common/TextToParagraphs";
import { Link, useSearchParams } from "react-router-dom";
import { URLS } from "../../urls";
import { twMerge } from "tailwind-merge";
import Popup from "../common/Popup";
import toast from "react-hot-toast";
import { useDatasetDrawer } from "../../context/DatasetDrawerContext";
import { Dataset, DatasetMember } from "../../api/client.schemas";
import { cellLayout } from "../../utils/cellLayout";
import { markAutoSelect } from "../../utils/autoSelect";

// initial page-size on the full page; "Show more" grows it in steps
const MAX_VISIBLE_GROUPS = 20;
const SHOW_MORE_STEP = 40;
// the sub-resource caps a page at 2000 groups
const MAX_EXPANDABLE_GROUPS = 2000;
// the drawer is read-only and image-first, so it shows a fixed preview
const MAX_VISIBLE_GROUPS_DRAWER = 24;
// newest N version chips shown before the "+N more" toggle
const MAX_VERSION_CHIPS = 6;
// a tile splits into at most this many role cells
const MAX_TILE_ROLES = 6;

// Shape of the rows ?include_fields=thumbnail_url merges into each member
// (backend/api/groups/expand.py), ordered by membership date_created.
interface ExpandedRole {
  image_id: string;
  role: string;
  thumbnail_url?: string | null;
}
type MemberWithRoles = DatasetMember & { roles?: ExpandedRole[] };

// Rendered both in the side drawer (data from useDatasetDrawer) and as a full
// page (data passed in via props). The drawer is a read-only, image-first
// preview: no mutations, no version chips, no per-group names — the full page
// carries all of that.
interface DatasetDetailProps {
  dataset?: Dataset;
  refetch?: () => void;
  onClose?: () => void;
  onFullPage?: boolean;
}

export const DatasetDetail: React.FC<DatasetDetailProps> = function ({
  dataset: datasetProp,
  refetch,
  onClose,
  onFullPage,
}) {
  const drawer = useDatasetDrawer();
  const dataset = datasetProp ?? drawer.dataset;
  const refetchDataset = refetch ?? drawer.refetchDataset;
  const closeDrawer = onClose ?? drawer.closeDrawer;
  const [searchParams, setSearchParams] = useSearchParams();

  // Full page only: which member roles resolve the preview thumbnails
  // (?cover_role=a,b CSV). With roles picked, every tile splits into one cell
  // per role, resolved client-side from the expanded per-role thumbnails —
  // a single role is just a 1-cell split, matching the groups view's
  // earliest-member-with-role semantics. The drawer keeps the default cover.
  const selectedRoles = onFullPage ? (searchParams.get("cover_role") ?? "").split(",").filter(Boolean) : [];
  const tileRoles = selectedRoles.slice(0, MAX_TILE_ROLES);

  // "Show more" grows the page size; keepPreviousData holds the current tiles
  // on screen while the bigger page (or a new role selection) loads.
  const [visibleCount, setVisibleCount] = useState(MAX_VISIBLE_GROUPS);
  const maxVisibleGroups = onFullPage ? visibleCount : MAX_VISIBLE_GROUPS_DRAWER;
  const {
    data: groupsData,
    isPending: isLoadingGroups,
    isFetching: isFetchingGroups,
  } = useDatasetsGroupsRetrieve(
    dataset?.slug_version ?? "",
    {
      page_size: maxVisibleGroups,
      // per-role thumbnails ride along only when roles are picked
      include_fields: tileRoles.length > 0 ? "thumbnail_url" : undefined,
      return_roles: tileRoles.length > 0 ? tileRoles.join(",") : undefined,
    },
    { query: { enabled: !!dataset, placeholderData: keepPreviousData } }
  );

  // The dataset's type declares which roles exist — they become the thumbnail
  // chips above the groups grid (full page only, the drawer has no chips).
  const { data: groupType } = useGroupTypesRetrieve(dataset?.type ?? "", {
    query: { enabled: !!dataset && !!onFullPage },
  });
  const availableRoles = groupType?.roles ?? [];

  // all versions of this dataset (same slug), so you can jump between them —
  // full page only; the drawer just shows the version it was opened on
  const { data: versionsData } = useDatasetsList(
    { slug: dataset?.slug ?? "", page_size: 100 },
    { query: { enabled: !!dataset && !!onFullPage } }
  );
  const versions = [...(versionsData?.results ?? [])].sort((a, b) => b.version - a.version);

  const { mutate: freezeDataset, isPending: isFreezing } = useDatasetsFreezeCreate();
  const { mutate: unfreezeDataset, isPending: isUnfreezing } = useDatasetsUnfreezeCreate();
  const { mutate: deleteDataset, isPending: isDeleting } = useDatasetsDestroy();
  const { mutate: partialUpdate } = useDatasetsPartialUpdate();

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionValue, setDescriptionValue] = useState("");
  const [showAllVersions, setShowAllVersions] = useState(false);

  if (!dataset) {
    return (
      <div className="w-full p-4">
        <p className="text-sm opacity-60">Loading dataset...</p>
      </div>
    );
  }

  const saveDescription = (value: string) => {
    const trimmed = value.trim();
    if (trimmed === dataset.description) {
      setEditingDescription(false);
      return;
    }
    partialUpdate(
      { slugVersion: dataset.slug_version, data: { description: trimmed } },
      {
        onSuccess: () => {
          toast.success("Description updated");
          refetchDataset();
          setEditingDescription(false);
        },
        onError: () => toast.error("Error updating description"),
      }
    );
  };

  // The groups sub-resource is a cursor page, so it carries no total: the dataset does.
  const groupCount = dataset.group_count;
  const groups: MemberWithRoles[] = groupsData?.results ?? [];
  const visibleGroups = groups.slice(0, maxVisibleGroups);
  // The dataset already knows its group_count, so the placeholder grid can be the size
  // the real grid will be: the tiles fill in where they sit, nothing reflows.
  const skeletonCount = Math.min(groupCount, maxVisibleGroups);
  // Use the server-resolved cover (earliest member group) so the banner matches
  // the list tile; the groups endpoint orders newest-first, so groups[0] wouldn't.
  const coverThumbnail = dataset.cover_thumbnail ?? groups[0]?.cover_thumbnail;

  // roles[] rows arrive ordered by membership date_created, so find() picks the
  // earliest member holding the role — same rule the groups view applies.
  const roleThumbnail = (member: MemberWithRoles, role: string) =>
    member.roles?.find(r => r.role === role)?.thumbnail_url ?? null;

  // Tile body: the group's default cover image, or one cell per selected role.
  const tileMedia = (member: MemberWithRoles) =>
    tileRoles.length > 0 ? (
      <div className={twMerge("grid h-full w-full gap-0.5 auto-rows-fr", cellLayout(tileRoles.length).colsClass)}>
        {tileRoles.map((role, i) => {
          const thumb = roleThumbnail(member, role);
          return (
            <div
              key={role}
              title={role}
              className={twMerge(
                "overflow-hidden bg-black/5 dark:bg-white/5",
                i === tileRoles.length - 1 ? cellLayout(tileRoles.length).lastSpanClass : ""
              )}
            >
              {thumb && <img src={thumb} alt="" loading="lazy" className="w-full h-full object-cover" />}
            </div>
          );
        })}
      </div>
    ) : (
      member.cover_thumbnail && (
        <img src={member.cover_thumbnail} alt="" loading="lazy" className="w-full h-full object-cover" />
      )
    );

  // Images filtered by this exact slug_version — reachable ONLY via the
  // explicit "View all images" link; every other entry point leads to the
  // groups view or the full dataset page.
  const imageSearchParams = new URLSearchParams(searchParams);
  imageSearchParams.set("datasets", dataset.slug_version);
  // The thumbnail role is a groups-view concept; it means nothing on the images page.
  imageSearchParams.delete("cover_role");

  // The primary "everything in this dataset" view: the groups page filtered
  // by this dataset, with its type already selected so role chips and
  // selection ("Add to dataset") work right away.
  const groupsUrl = URLS.GROUP_LIST(new URLSearchParams({ dataset: dataset.slug_version, type: dataset.type }));
  // Entry point for filling an empty dataset: the groups page pre-filtered to
  // the dataset's type; markAutoSelect on the link opens selection on arrival.
  const addGroupsUrl = URLS.GROUP_LIST(new URLSearchParams({ type: dataset.type }));
  const detailUrl = URLS.DATASET_DETAIL(dataset.slug, dataset.version);

  // Chips are multi-select: toggling composes the CSV, the "cover" chip clears it.
  const setRoles = (roles: string[]) => {
    const next = new URLSearchParams(searchParams);
    if (roles.length) next.set("cover_role", roles.join(","));
    else next.delete("cover_role");
    setSearchParams(next);
  };
  const toggleRole = (role: string) =>
    setRoles(selectedRoles.includes(role) ? selectedRoles.filter(r => r !== role) : [...selectedRoles, role]);

  // -------------------- Drawer: compact, read-only, image-first --------------------
  if (!onFullPage) {
    return (
      <div className="flex flex-col gap-4 px-4 pt-4 pb-8 text-sm">
        {/* Compact cover — opens the dataset page; the counter pill opens the groups
            view. An empty dataset instead links to the groups page pre-filtered to
            its type, ready for selecting and adding. */}
        <div className="relative">
          <Link
            to={groupCount === 0 ? addGroupsUrl : detailUrl}
            onClick={groupCount === 0 ? markAutoSelect : undefined}
            className="block h-40 rounded-lg overflow-hidden bg-black/5 dark:bg-white/5 group"
          >
            {coverThumbnail ? (
              <img
                src={coverThumbnail}
                alt=""
                className="w-full h-full object-cover group-hover:scale-[102%] transition-transform"
              />
            ) : (
              <div className="flex flex-col items-center justify-center gap-1 h-full text-xs">
                {groupCount > 0 ? (
                  <span className="opacity-30">Groups are being indexed...</span>
                ) : (
                  <>
                    <span className="opacity-30">No groups yet</span>
                    <span className="inline-flex items-center gap-0.5 text-primary-500">
                      <PlusIcon className="size-3.5" />
                      Add groups
                    </span>
                  </>
                )}
              </div>
            )}
          </Link>
          <Link
            to={groupsUrl}
            className="absolute bottom-2 right-2 px-2 py-0.5 rounded-full bg-black/60 text-white text-[11px] font-medium hover:bg-black/80 transition-colors"
          >
            {formatNumber(groupCount, { decimals: 0 })} groups
          </Link>
          <Link
            to={detailUrl}
            title="Open dataset"
            className="absolute top-2 right-2 p-1.5 rounded-full bg-black/60 text-white hover:bg-black/80 transition-colors"
          >
            <ArrowTopRightOnSquareIcon className="size-4" />
          </Link>
        </div>

        {/* Title + meta */}
        <div className="flex flex-col gap-1 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <Link to={detailUrl} className="min-w-0 hover:opacity-70 transition-opacity">
              <h4 className="text-lg font-bold leading-tight break-words">{dataset.name}</h4>
            </Link>
          </div>
          <span className="text-xs font-mono opacity-40">{dataset.slug_version}</span>
          <p className="text-xs opacity-40">
            {dataset.author?.email && <>by {dataset.author.email} &middot; </>}
            updated {new Date(dataset.date_updated).toLocaleDateString()}
          </p>
          <div className="flex items-center gap-1.5 flex-wrap mt-1">
            <span className="text-[10px] font-medium uppercase px-2 py-0.5 rounded-full bg-brand-100 text-brand-700 dark:bg-brand-900 dark:text-brand-300">
              {dataset.type}
            </span>
            {dataset.is_frozen && (
              <span className="text-[10px] font-medium uppercase px-2 py-0.5 rounded-full bg-cyan-400/40 dark:bg-cyan-600/40">
                frozen
              </span>
            )}
          </div>
        </div>

        {dataset.description && <TextToParagraphs text={dataset.description} className="text-sm opacity-70" />}

        {/* Groups preview — image-first, names live on the full page */}
        {((isLoadingGroups && skeletonCount > 0) || groups.length > 0) && (
          <div>
            <div className="flex items-baseline justify-between mb-2">
              <h5 className="text-xs font-semibold uppercase tracking-wider opacity-50">Groups</h5>
              <Link to={groupsUrl} className="text-xs text-primary-500 hover:underline">
                show all {formatNumber(groupCount, { decimals: 0 })} &rarr;
              </Link>
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {isLoadingGroups
                ? Array.from({ length: skeletonCount }, (_, i) => (
                    <div key={i} className="aspect-square rounded-lg bg-black/5 dark:bg-white/5 animate-pulse" />
                  ))
                : visibleGroups.map(group => (
                    <Link
                      key={group.id}
                      to={URLS.GROUP_DETAIL(group.id)}
                      className="aspect-square rounded-lg bg-black/5 dark:bg-white/5 overflow-hidden hover:opacity-90 transition-opacity"
                    >
                      {group.cover_thumbnail && (
                        <img src={group.cover_thumbnail} alt="" loading="lazy" className="w-full h-full object-cover" />
                      )}
                    </Link>
                  ))}
            </div>
            <Link
              to={URLS.IMAGE_LIST(imageSearchParams)}
              className="inline-flex items-center gap-1 mt-2 text-xs text-primary-500 hover:underline"
            >
              <PhotoIcon className="size-3.5" />
              View all images &rarr;
            </Link>
          </div>
        )}
      </div>
    );
  }

  // -------------------- Full page --------------------
  return (
    <>
      {/* Cover image banner — desktop only; opens the groups view, as does the
          counter pill (a sibling link — nested links are invalid HTML). An empty
          dataset instead links to the groups page pre-filtered to its type,
          arriving with selection mode already open. */}
      <div className="relative hidden sm:block">
        <Link
          to={groupCount === 0 ? addGroupsUrl : groupsUrl}
          onClick={groupCount === 0 ? markAutoSelect : undefined}
          className="block relative w-full sm:h-64 md:h-80 lg:h-96 bg-black/5 dark:bg-white/5 overflow-hidden cursor-pointer group"
        >
          {coverThumbnail ? (
            <>
              <div
                className="absolute inset-0 bg-cover bg-center scale-110 blur-2xl opacity-40"
                style={{ backgroundImage: `url(${coverThumbnail})` }}
              />
              <img src={coverThumbnail} alt="" className="relative w-full h-full object-contain" />
              <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/50 to-transparent" />
              <span className="absolute inset-0 bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity" />
            </>
          ) : (
            <div className="flex flex-col items-center justify-center gap-1 h-full">
              {groupCount > 0 ? (
                <span className="text-sm opacity-30">Groups are being indexed...</span>
              ) : (
                <>
                  <span className="text-sm opacity-30">No groups yet</span>
                  <span className="inline-flex items-center gap-1 text-sm text-primary-500">
                    <PlusIcon className="size-4" />
                    Add groups
                  </span>
                  <span className="text-xs opacity-30">
                    pick {dataset.type} groups, then &ldquo;Add to dataset&rdquo;
                  </span>
                </>
              )}
            </div>
          )}
        </Link>
        {coverThumbnail && (
          <Link
            to={groupsUrl}
            className="absolute bottom-4 right-4 px-3 py-1 rounded-full bg-black/60 text-white text-xs font-medium hover:bg-black/80 transition-colors"
          >
            {formatNumber(groupCount, { decimals: 0 })} groups
          </Link>
        )}
      </div>

      {/* Content */}
      <div className="max-w-6xl mx-auto w-full px-3 py-3 sm:px-6 sm:py-6">
        {/* Back link */}
        <Link
          to={URLS.DATASET_LIST()}
          className="flex items-center gap-1 text-xs sm:text-sm opacity-40 hover:opacity-100 w-fit mb-2 sm:mb-4"
        >
          <ArrowLeftIcon className="w-3 h-3" />
          Datasets
        </Link>

        {/* Title + meta */}
        <div className="flex flex-col gap-2 sm:gap-3 mb-4 sm:mb-6">
          {/* Title row */}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h1 className="text-lg sm:text-2xl md:text-3xl font-bold leading-tight">{dataset.name}</h1>
              <span className="text-xs font-mono opacity-30">{dataset.slug_version}</span>
            </div>
          </div>

          {/* Type + version + frozen badges */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] font-medium uppercase px-2 py-1 rounded-full bg-brand-100 text-brand-700 dark:bg-brand-900 dark:text-brand-300">
              {dataset.type}
            </span>
            <span className="text-[10px] font-medium uppercase px-2 py-1 rounded-full bg-black/10 dark:bg-white/10">
              v{dataset.version}
            </span>
            <span className="text-[10px] font-medium uppercase px-2 py-1 rounded-full bg-black/10 dark:bg-white/10">
              {formatNumber(groupCount, { decimals: 0 })} groups
            </span>
            {dataset.is_frozen && (
              <span className="text-[10px] font-medium uppercase px-2 py-1 rounded-full bg-cyan-400/40 dark:bg-cyan-600/40">
                frozen
              </span>
            )}
          </div>

          {/* Links — images-filtered view is the special case, reachable only here */}
          <div className="flex items-center gap-3 flex-wrap text-sm">
            <Link
              to={URLS.IMAGE_LIST(imageSearchParams)}
              className="inline-flex items-center gap-1 text-primary-500 hover:underline"
            >
              <PhotoIcon className="size-4" />
              View all images
            </Link>
          </div>

          {/* Versions — jump between versions of this dataset */}
          {versions.length > 1 && (
            <div className="flex items-center gap-1.5 flex-wrap text-sm">
              <span className="text-xs opacity-50">Versions:</span>
              {(showAllVersions ? versions : versions.slice(0, MAX_VERSION_CHIPS)).map(v => {
                const isCurrent = v.slug_version === dataset.slug_version;
                const to = URLS.DATASET_DETAIL(v.slug, v.version);
                return (
                  <Link
                    key={v.slug_version}
                    to={to}
                    title={`${v.group_count} items`}
                    className={twMerge(
                      "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs transition-colors",
                      isCurrent
                        ? "bg-brand-100 text-brand-700 font-bold dark:bg-brand-900 dark:text-brand-200"
                        : "bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/20"
                    )}
                  >
                    <span>v{v.version}</span>
                    <span className="text-[9px] leading-none px-1 py-0.5 rounded-full bg-black/10 dark:bg-white/25 tabular-nums font-normal">
                      {formatNumber(v.group_count, { decimals: 0 })}
                    </span>
                    {v.is_frozen && <span aria-label="frozen">🔒</span>}
                  </Link>
                );
              })}
              {versions.length > MAX_VERSION_CHIPS && (
                <button
                  type="button"
                  onClick={() => setShowAllVersions(s => !s)}
                  className="text-xs opacity-60 hover:opacity-100 hover:underline cursor-pointer"
                >
                  {showAllVersions ? "show less" : `+${versions.length - MAX_VERSION_CHIPS} more`}
                </button>
              )}
            </div>
          )}

          {/* Action buttons — the drawer is read-only, mutations live here only */}
          <div className="flex items-center gap-1.5 flex-wrap">
            {dataset.is_frozen ? (
              <button
                type="button"
                className="btn btn-sm btn-outline"
                disabled={isUnfreezing}
                onClick={() => {
                  unfreezeDataset(
                    { slugVersion: dataset.slug_version, data: dataset },
                    {
                      onSuccess: () => {
                        toast.success("Dataset unfrozen");
                        refetchDataset();
                      },
                      onError: () => toast.error("Error unfreezing dataset"),
                    }
                  );
                }}
              >
                <LockOpenIcon />
                <span>{isUnfreezing ? "..." : "Unfreeze"}</span>
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-sm btn-outline"
                disabled={isFreezing}
                onClick={() => {
                  freezeDataset(
                    { slugVersion: dataset.slug_version, data: dataset },
                    {
                      onSuccess: () => {
                        toast.success(`Dataset "${dataset.name}" frozen`);
                        refetchDataset();
                      },
                      onError: () => toast.error("Error freezing dataset"),
                    }
                  );
                }}
              >
                <LockClosedIcon />
                <span>{isFreezing ? "..." : "Freeze"}</span>
              </button>
            )}
            <button
              type="button"
              className="btn btn-sm btn-outline shrink-0"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={isDeleting}
            >
              <TrashIcon />
            </button>
          </div>

          {/* Author + dates */}
          <p className="text-xs opacity-40">
            {dataset.author?.email && <>by {dataset.author.email} &middot; </>}
            {new Date(dataset.date_created).toLocaleDateString()}
            {dataset.date_updated !== dataset.date_created && (
              <> &middot; updated {new Date(dataset.date_updated).toLocaleDateString()}</>
            )}
          </p>

          {/* Description — click-to-edit */}
          {editingDescription ? (
            <textarea
              autoFocus
              className="text-sm w-full bg-transparent border border-current/30 rounded-lg p-2 outline-none resize-none"
              rows={4}
              value={descriptionValue}
              onChange={e => setDescriptionValue(e.target.value)}
              onBlur={() => saveDescription(descriptionValue)}
              onKeyDown={e => {
                if (e.key === "Escape") setEditingDescription(false);
              }}
            />
          ) : (
            <div
              className="cursor-pointer hover:opacity-70 transition-opacity"
              onClick={() => {
                setDescriptionValue(dataset.description ?? "");
                setEditingDescription(true);
              }}
            >
              {dataset.description ? (
                <TextToParagraphs text={dataset.description} className="text-sm opacity-70" />
              ) : (
                <p className="text-sm opacity-20 italic">Click to add a description...</p>
              )}
            </div>
          )}
        </div>

        {/* Member groups grid */}
        {groupCount > 0 && (
          <div className="mb-6">
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-sm font-semibold opacity-50 uppercase tracking-wider">
                Groups
                {groupCount > maxVisibleGroups && (
                  <span className="ml-2 font-normal normal-case opacity-70">
                    showing first {maxVisibleGroups} of {formatNumber(groupCount, { decimals: 0 })}
                  </span>
                )}
              </h2>
              <Link to={groupsUrl} className="text-sm text-primary-500 hover:underline">
                show all {formatNumber(groupCount, { decimals: 0 })} &rarr;
              </Link>
            </div>

            {/* Thumbnail role chips — like the groups view sidebar, but
                multi-select: each picked role becomes a cell in every tile
                (?cover_role=a,b). "cover" clears back to the default cover. */}
            {availableRoles.length > 0 && (
              <div className="flex flex-wrap items-center gap-1 mb-3">
                <span className="text-[10px] uppercase tracking-wide opacity-50 mr-1">Thumbnail</span>
                <button
                  type="button"
                  onClick={() => setRoles([])}
                  title="The group's default cover: its explicit cover image, else the first image added"
                  className={twMerge(
                    "text-xs px-2 py-0.5 rounded-full border transition-colors cursor-pointer",
                    selectedRoles.length === 0
                      ? "bg-brand-400/20 border-brand-400/40 text-brand-500 dark:text-brand-400 font-medium"
                      : "border-black/10 dark:border-white/10 opacity-60 hover:opacity-100"
                  )}
                >
                  cover
                </button>
                {availableRoles.map(r => (
                  <button
                    key={r.role}
                    type="button"
                    onClick={() => toggleRole(r.role)}
                    title={r.is_required ? `${r.role} (required role)` : r.role}
                    className={twMerge(
                      "text-xs px-2 py-0.5 rounded-full border transition-colors cursor-pointer",
                      selectedRoles.includes(r.role)
                        ? "bg-brand-400/20 border-brand-400/40 text-brand-500 dark:text-brand-400 font-medium"
                        : "border-black/10 dark:border-white/10 opacity-60 hover:opacity-100"
                    )}
                  >
                    {r.role}
                  </button>
                ))}
                {selectedRoles.length > MAX_TILE_ROLES && (
                  <span className="text-[10px] opacity-50">showing the first {MAX_TILE_ROLES} roles per tile</span>
                )}
              </div>
            )}

            <div
              className={twMerge(
                "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-5 gap-3 sm:gap-4",
                // previous tiles stay visible (keepPreviousData) while a role
                // switch or "Show more" loads; dim them as feedback
                isFetchingGroups && !isLoadingGroups && "opacity-60 transition-opacity"
              )}
            >
              {isLoadingGroups
                ? Array.from({ length: skeletonCount }, (_, i) => (
                    <div key={i} className="aspect-square rounded-lg bg-black/5 dark:bg-white/5 animate-pulse" />
                  ))
                : visibleGroups.map(group => (
                    <Link key={group.id} to={URLS.GROUP_DETAIL(group.id)} className="flex flex-col gap-1 group">
                      <div
                        className={twMerge(
                          "aspect-square rounded-lg bg-black/5 dark:bg-white/5 overflow-hidden",
                          "ring-1 ring-black/8 dark:ring-white/8",
                          "group-hover:opacity-90 transition-opacity"
                        )}
                      >
                        {tileMedia(group)}
                      </div>
                      <span className="text-[11px] opacity-60 truncate">{group.name}</span>
                    </Link>
                  ))}
            </div>

            {/* Expand in place, up to the sub-resource's page cap */}
            {groupCount > visibleCount && visibleCount < MAX_EXPANDABLE_GROUPS && (
              <div className="flex justify-center mt-4">
                <button
                  type="button"
                  className="btn btn-sm btn-outline"
                  disabled={isFetchingGroups}
                  onClick={() => setVisibleCount(c => Math.min(c + SHOW_MORE_STEP, MAX_EXPANDABLE_GROUPS))}
                >
                  {isFetchingGroups
                    ? "Loading..."
                    : `Show ${formatNumber(Math.min(SHOW_MORE_STEP, groupCount - visibleCount), { decimals: 0 })} more`}
                </button>
              </div>
            )}
          </div>
        )}

        {groupCount === 0 && (
          <div className="flex flex-col gap-1 text-sm">
            <p className="flex items-center gap-2">
              <span className="opacity-30 italic">No groups in this dataset yet.</span>
              <Link
                to={addGroupsUrl}
                onClick={markAutoSelect}
                className="inline-flex items-center gap-0.5 text-primary-500 hover:underline"
              >
                <PlusIcon className="size-4" />
                Add groups
              </Link>
            </p>
            <p className="text-xs opacity-40">pick {dataset.type} groups there, then &ldquo;Add to dataset&rdquo;</p>
          </div>
        )}
      </div>

      {/* Delete confirm */}
      {showDeleteConfirm && (
        <Popup onClose={() => setShowDeleteConfirm(false)}>
          <div className="flex flex-col gap-4">
            <h3 className="text-lg font-bold">Delete dataset version</h3>
            <p className="text-sm opacity-70">
              Are you sure you want to delete{" "}
              <strong>
                {dataset.name} v{dataset.version}
              </strong>
              ? This will remove the dataset record but will not delete the groups themselves.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => setShowDeleteConfirm(false)}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn bg-rose-500 text-white hover:bg-rose-600"
                disabled={isDeleting}
                onClick={() => {
                  deleteDataset(
                    { slugVersion: dataset.slug_version },
                    {
                      onSuccess: () => {
                        toast.success(`Deleted ${dataset.name} v${dataset.version}`);
                        setShowDeleteConfirm(false);
                        closeDrawer();
                      },
                      onError: () => toast.error("Error deleting dataset"),
                    }
                  );
                }}
              >
                {isDeleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </Popup>
      )}
    </>
  );
};
