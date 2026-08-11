import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { ArrowRightIcon, ArrowTopRightOnSquareIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { useGroupDrawer } from "../../context/GroupDrawerContext";
import { useGroupTypesRetrieve, useImagesList } from "../../api/client";
import { formatNumber } from "../../utils/formatNumber";
import { TextToParagraphs } from "../../components/common/TextToParagraphs";
import { LoaderSkeleton } from "../../components/common/LoaderSkeleton";
import { URLS } from "../../urls";

// Light preview only — the full member list / role metadata lives on the detail page.
const PREVIEW_SIZE = 6;

// At most this many role pills per thumbnail; the rest collapse into a "+N more".
const MAX_VISIBLE_ROLES = 2;

const ROLE_PILL_CLASS =
  "max-w-full truncate rounded-full bg-black/40 text-white/90 text-[10px] font-medium tracking-wide px-1.5 py-0.5";

// Role pills overlaid on a member thumbnail (like the type pill on a group card).
// Caps at MAX_VISIBLE_ROLES and shows "+N more" when an image holds extra roles.
export const MemberRolePills: React.FC<{ roles: string[] }> = function ({ roles }) {
  if (roles.length === 0) return null;
  const visible = roles.slice(0, MAX_VISIBLE_ROLES);
  const hidden = roles.length - visible.length;
  return (
    <div className="absolute top-1 left-1 right-1 flex flex-wrap gap-0.5">
      {visible.map(role => (
        <span key={role} title={role} className={ROLE_PILL_CLASS}>
          {role}
        </span>
      ))}
      {hidden > 0 && (
        <span title={roles.slice(MAX_VISIBLE_ROLES).join(", ")} className={ROLE_PILL_CLASS}>
          +{hidden} more
        </span>
      )}
    </div>
  );
};

// "Open full details" — only needs the id, so it renders even while the group
// itself is still loading (or errored), keeping the full view always reachable.
const OpenFullDetailsLink: React.FC<{ groupId: string }> = function ({ groupId }) {
  return (
    <Link
      to={URLS.GROUP_DETAIL(groupId)}
      className="flex items-center gap-1.5 self-start mt-1 px-3 py-1.5 rounded-lg border border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors font-medium"
    >
      Open full details
      <ArrowRightIcon className="size-3.5" />
    </Link>
  );
};

export const GroupsDrawerContent: React.FC = function () {
  const { group, groupId, closeDrawer } = useGroupDrawer();

  // Roles defined on the group's type (names + required flag) — cheap, cached lookup.
  const { data: groupType } = useGroupTypesRetrieve(group?.type ?? "", {
    query: { enabled: Boolean(group?.type) },
  });

  // A handful of member thumbnails for the preview strip. Pull in each image's
  // `memberships` denorm so we can read its role(s) in this group directly off
  // the image — robust for every previewed image, no separate paged fetch.
  const { data: previewData, isLoading: isLoadingPreview } = useImagesList(
    { group_ids: [groupId], page_size: PREVIEW_SIZE, include_fields: "thumbnail,image,memberships" },
    { query: { enabled: Boolean(groupId) } }
  );
  const previews = previewData?.results ?? [];

  // Each membership entry is encoded "<role>::<type>::<uuid>" — slice off the
  // roles that belong to THIS group (its type + id) for the pill overlay.
  const rolesByImage = useMemo(() => {
    const map = new Map<string, string[]>();
    if (!group) return map;
    const suffix = `::${group.type}::${groupId}`;
    for (const img of previews) {
      const roles: string[] = [];
      for (const entry of img.memberships ?? []) {
        if (entry.endsWith(suffix)) {
          const role = entry.slice(0, entry.length - suffix.length);
          if (role && !roles.includes(role)) roles.push(role);
        }
      }
      if (roles.length > 0) map.set(img.id, roles);
    }
    return map;
  }, [previews, group, groupId]);

  const imageListParams = new URLSearchParams({ group_ids: groupId });

  if (!group) {
    return (
      <div className="flex flex-col gap-4 px-4 pt-4 pb-6 md:max-w-drawer text-sm">
        <LoaderSkeleton className="h-6 w-1/2" />
        <LoaderSkeleton className="h-4 w-1/3" />
        <LoaderSkeleton className="h-40 w-full" />
        {groupId && <OpenFullDetailsLink groupId={groupId} />}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 px-4 pt-4 pb-20 md:max-w-drawer text-sm">
      {/* Header: title + close */}
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <h4 className="text-lg font-bold leading-tight break-words min-w-0">{group.name}</h4>
            <Link
              to={URLS.GROUP_DETAIL(groupId)}
              title="Open full details"
              className="shrink-0 opacity-40 hover:opacity-100 transition-opacity"
            >
              <ArrowTopRightOnSquareIcon className="size-4" />
            </Link>
          </div>
          <span className="text-[10px] font-medium uppercase px-1.5 py-0.5 rounded-full bg-black/10 dark:bg-white/10">
            {group.type}
          </span>
          {groupType?.description && <p className="mt-1 text-xs opacity-50">{groupType.description}</p>}
        </div>
        <button
          type="button"
          onClick={closeDrawer}
          title="Close panel"
          className="shrink-0 p-1 -mt-1 -mr-1 rounded-md opacity-50 hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer transition-colors"
        >
          <XMarkIcon className="size-5" />
        </button>
      </div>

      {/* Meta */}
      <div className="flex flex-col gap-1">
        <Link to={URLS.IMAGE_LIST(imageListParams)} className="opacity-70 hover:underline w-fit">
          {formatNumber(group.image_count, { decimals: 0 })} images
        </Link>
        {group.author?.email && <p className="text-xs opacity-50">by {group.author.email}</p>}
        <p className="text-xs opacity-50" title={group.date_created}>
          Created {new Date(group.date_created).toLocaleDateString()}
        </p>
      </div>

      {group.description && <TextToParagraphs text={group.description} className="opacity-80" />}

      {/* Roles */}
      {(groupType?.roles ?? []).length > 0 && (
        <div className="flex flex-col gap-2">
          <h5 className="text-[11px] font-bold uppercase tracking-wide opacity-50">Roles</h5>
          <div className="flex flex-row flex-wrap gap-1.5">
            {(groupType?.roles ?? []).map(r => (
              <span
                key={r.role}
                title={r.is_required ? "Required role" : undefined}
                className={
                  r.is_required
                    ? "text-xs font-medium px-2 py-0.5 rounded-full bg-brand-500/20 text-brand-700 dark:text-brand-300"
                    : "text-xs font-medium px-2 py-0.5 rounded-full bg-black/10 dark:bg-white/10"
                }
              >
                {r.role}
                {r.is_required && <span className="opacity-70 ml-0.5">*</span>}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Members preview */}
      <div className="flex flex-col gap-2">
        <h5 className="text-[11px] font-bold uppercase tracking-wide opacity-50">
          Members
          {group.image_count > previews.length && (
            <span className="ml-1.5 normal-case font-normal tracking-normal">
              showing first {previews.length} of {formatNumber(group.image_count, { decimals: 0 })}
            </span>
          )}
        </h5>
        {isLoadingPreview && previews.length === 0 ? (
          <div className="grid grid-cols-2 gap-1.5">
            {Array.from({ length: 4 }).map((_, i) => (
              <LoaderSkeleton key={i} className="aspect-square rounded-md" />
            ))}
          </div>
        ) : previews.length === 0 ? (
          <p className="opacity-50">No members yet.</p>
        ) : (
          <Link to={URLS.IMAGE_LIST(imageListParams)} className="grid grid-cols-2 gap-1.5 group">
            {previews.map(img => {
              const roles = rolesByImage.get(img.id) ?? [];
              return (
                <div
                  key={img.id}
                  className="relative aspect-square rounded-md overflow-hidden bg-black/5 dark:bg-white/5 group-hover:opacity-90 transition-opacity"
                >
                  {(img.thumbnail || img.image) && (
                    <img
                      src={img.thumbnail || img.image}
                      alt=""
                      loading="lazy"
                      className="w-full h-full object-cover"
                    />
                  )}
                  <MemberRolePills roles={roles} />
                </div>
              );
            })}
          </Link>
        )}
      </div>

      {/* Full details */}
      <OpenFullDetailsLink groupId={groupId} />
    </div>
  );
};
