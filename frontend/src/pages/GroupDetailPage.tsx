import React, { useEffect, useMemo, useState } from "react";
import { twMerge } from "tailwind-merge";
import { ArrowLeftIcon, ListBulletIcon, Squares2X2Icon } from "@heroicons/react/24/outline";
import { Link, useParams } from "react-router-dom";
import { toast } from "react-hot-toast";
import { MainContainer } from "../layouts/MainContainer";
import { useGroupsRetrieve, useGroupTypesRetrieve, useImagesList, useGroupsMembersList } from "../api/client";
import { LoaderSkeleton } from "../components/common/LoaderSkeleton";
import { JsonHighlight } from "../components/common/JsonHighlight";
import { ZoomableImage } from "../components/image/ZoomableImage";
import { MemberRolePills } from "../layouts/groups/GroupsDrawerContent";
import { TextToParagraphs } from "../components/common/TextToParagraphs";
import { formatNumber } from "../utils/formatNumber";
import { URLS } from "../urls";
import { Membership, OSImage } from "../api/client.schemas";

// Load all members; the list scrolls within a fixed-height box regardless of count.
const MEMBERS_PAGE_SIZE = 200;

// Metadata renders as pretty JSON; large blobs are cropped to a max height and
// scroll within it (see usages below).
const META_CLASS = "max-h-80";

// One card per image, carrying every role (membership) that image holds.
interface ImageMembers {
  image_id: string;
  roles: Membership[];
}

interface MemberRowProps {
  member: ImageMembers;
  image?: OSImage;
  isCover?: boolean;
}

// Sidebar shown in the enlarged (zoomed) image view: every role this image
// holds in the group, each with its metadata.
const MemberRolesPanel: React.FC<{ member: ImageMembers }> = ({ member }) => (
  <div className="p-4 flex flex-col gap-4">
    <div className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wide opacity-50">Image</span>
      <Link
        to={URLS.IMAGE_DETAIL(member.image_id)}
        className="text-xs font-mono break-all opacity-70 hover:opacity-100 hover:underline"
      >
        {member.image_id}
      </Link>
    </div>
    <div className="flex flex-col gap-3">
      <span className="text-[10px] uppercase tracking-wide opacity-50">
        Roles &amp; metadata ({member.roles.length})
      </span>
      {member.roles.map(m => {
        const hasMeta = m.metadata && Object.keys(m.metadata).length > 0;
        return (
          <div key={m.id} className="flex flex-col gap-1">
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-black/10 dark:bg-white/10 self-start">
              {m.role}
            </span>
            {hasMeta ? (
              <JsonHighlight value={m.metadata} deep className={META_CLASS} />
            ) : (
              <p className="text-xs opacity-50">No metadata.</p>
            )}
          </div>
        );
      })}
    </div>
  </div>
);

// Thumbnail + role chips (chips act as tabs when an image has several roles).
// Metadata for the selected role is always shown below. Click the image to
// enlarge and see every role + metadata (MemberRolesPanel) in the zoom sidebar.
const MemberRow: React.FC<MemberRowProps> = ({ member, image, isCover }) => {
  const [selectedRole, setSelectedRole] = useState(member.roles[0]?.role);
  const [zoomOpen, setZoomOpen] = useState(false);
  const [metaExpanded, setMetaExpanded] = useState(false);
  const selected = member.roles.find(m => m.role === selectedRole) ?? member.roles[0];
  const selectedHasMeta = Boolean(selected?.metadata && Object.keys(selected.metadata).length > 0);
  const multiRole = member.roles.length > 1;

  return (
    // The whole row is clickable to open the enlarged view; nested links/chips
    // stopPropagation so they keep their own behaviour. Slight hover grow as a
    // affordance that the row is interactive.
    <div
      onClick={() => setZoomOpen(true)}
      title="Click to enlarge"
      className={twMerge(
        "shrink-0 border border-black/10 dark:border-white/10 rounded-lg overflow-hidden flex items-stretch cursor-pointer transition-[transform,height] transform-gpu hover:scale-[1.03] hover:border-black/20 dark:hover:border-white/20",
        metaExpanded ? "h-80 sm:h-96" : "h-36 sm:h-40"
      )}
    >
      <ZoomableImage
        image={image}
        sidebar={<MemberRolesPanel member={member} />}
        open={zoomOpen}
        onOpenChange={setZoomOpen}
        className="block w-36 h-36 sm:w-40 sm:h-40 shrink-0 bg-black/5 dark:bg-white/5 overflow-hidden group cursor-zoom-in"
      >
        {image && (image.thumbnail || image.image) && (
          <img
            src={image.thumbnail || image.image}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover transition-transform group-hover:scale-105"
          />
        )}
      </ZoomableImage>
      <div className="flex flex-col gap-1.5 px-3 py-2 min-w-0 flex-1 overflow-hidden">
        <div className="flex items-center gap-2 min-w-0 shrink-0">
          <Link
            to={URLS.IMAGE_DETAIL(member.image_id)}
            onClick={e => e.stopPropagation()}
            className="text-[11px] opacity-40 hover:opacity-80 hover:underline truncate font-mono max-w-full"
          >
            {member.image_id}
          </Link>
          {isCover && (
            <span className="shrink-0 text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-brand-500/20 text-brand-700 dark:text-brand-300">
              main
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1 shrink-0">
          {member.roles.map(m => {
            const hasMeta = m.metadata && Object.keys(m.metadata).length > 0;
            const active = m.role === selected?.role;
            const dot = hasMeta && <span className="size-1 rounded-full bg-current opacity-60" />;
            return (
              <button
                key={m.id}
                type="button"
                onClick={e => {
                  e.stopPropagation();
                  setSelectedRole(m.role);
                }}
                title={multiRole ? `Show ${m.role} metadata` : m.role}
                className={twMerge(
                  "text-xs font-medium px-2 py-0.5 rounded-full transition-colors inline-flex items-center gap-1",
                  multiRole && "cursor-pointer",
                  active && multiRole
                    ? "bg-brand-500 text-white"
                    : "bg-black/10 dark:bg-white/10 hover:bg-black/20 dark:hover:bg-white/20"
                )}
              >
                {m.role}
                {dot}
              </button>
            );
          })}
        </div>
        {/* Fills the leftover row height and scrolls; "Show more" grows the row
            so large metadata is readable without the cramped scroll. */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          {selected &&
            (selectedHasMeta ? (
              <JsonHighlight value={selected.metadata} deep />
            ) : (
              <p className="text-xs italic opacity-30">No metadata.</p>
            ))}
        </div>
        {selectedHasMeta && (
          <button
            type="button"
            onClick={e => {
              e.stopPropagation();
              setMetaExpanded(v => !v);
            }}
            className="shrink-0 self-start text-[11px] text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:underline cursor-pointer"
          >
            {metaExpanded ? "Show less" : "Show more"}
          </button>
        )}
      </div>
    </div>
  );
};

// Compact-view tile: just the square thumbnail with role pills overlaid; click
// to zoom for the full roles + metadata panel. Lets many members fit at once.
const MemberTile: React.FC<MemberRowProps> = ({ member, image, isCover }) => {
  const roles = useMemo(() => Array.from(new Set(member.roles.map(r => r.role))), [member.roles]);
  return (
    <div className="relative aspect-square rounded-lg overflow-hidden border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 group transition-transform transform-gpu hover:scale-[1.03] hover:border-black/20 dark:hover:border-white/20">
      <ZoomableImage
        image={image}
        sidebar={<MemberRolesPanel member={member} />}
        className="absolute inset-0 block w-full h-full cursor-zoom-in"
      >
        {image && (image.thumbnail || image.image) && (
          <img
            src={image.thumbnail || image.image}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover transition-transform group-hover:scale-105"
          />
        )}
      </ZoomableImage>
      {/* pointer-events-none so a click anywhere lands on the zoom button below */}
      <div className="pointer-events-none">
        <MemberRolePills roles={roles} />
      </div>
      {isCover && (
        <span className="absolute bottom-1 right-1 text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-brand-500 text-white">
          main
        </span>
      )}
    </div>
  );
};

// Above this many serialized lines the rail metadata is clamped behind a
// "Show more" toggle so it never dominates the narrow info column.
const META_COLLAPSE_LINES = 8;

const GroupMetadataPanel: React.FC<{ metadata: Record<string, unknown> }> = function ({ metadata }) {
  const [expanded, setExpanded] = useState(false);
  const isLarge = useMemo(() => {
    try {
      return JSON.stringify(metadata, null, 2).split("\n").length > META_COLLAPSE_LINES;
    } catch {
      return false;
    }
  }, [metadata]);

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-bold uppercase tracking-wide opacity-60">Metadata</h2>
      <JsonHighlight value={metadata} className={!isLarge || expanded ? "max-h-96" : "max-h-28 overflow-hidden"} />
      {isLarge && (
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:underline w-fit cursor-pointer"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </section>
  );
};

export const GroupDetailPage: React.FC = function () {
  const { groupId = "" } = useParams<{ groupId: string }>();
  const { data: group, isLoading, isError } = useGroupsRetrieve(groupId);
  const { data: groupType } = useGroupTypesRetrieve(group?.type ?? "", {
    query: { enabled: Boolean(group?.type) },
  });
  const { data: previewData, isLoading: isLoadingPreview } = useImagesList(
    { group_ids: [groupId], page_size: MEMBERS_PAGE_SIZE, include_fields: "thumbnail,image" },
    { query: { enabled: Boolean(groupId) } }
  );
  const { data: membersData, isLoading: isLoadingMembers } = useGroupsMembersList(
    groupId,
    { page_size: MEMBERS_PAGE_SIZE },
    { query: { enabled: Boolean(groupId) } }
  );

  // In-page role filter: clicking a role chip in the Roles section toggles it;
  // the list shows images holding ANY selected role.
  const [roleFilter, setRoleFilter] = useState<string[]>([]);
  const toggleRoleFilter = (role: string) =>
    setRoleFilter(prev => (prev.includes(role) ? prev.filter(r => r !== role) : [...prev, role]));

  // Members density: "comfortable" = big rows with inline metadata; "compact" =
  // a grid of small thumbnails to scan many members at once.
  const [memberView, setMemberView] = useState<"comfortable" | "compact">("comfortable");

  useEffect(() => {
    if (isError) {
      toast.error("Error loading group");
    }
  }, [isError]);

  const allMembersParams = new URLSearchParams({ group_ids: groupId });

  const imagesById = useMemo(() => {
    const map = new Map<string, OSImage>();
    for (const img of previewData?.results ?? []) {
      map.set(img.id, img);
    }
    return map;
  }, [previewData]);

  // Collapse the flat membership list to one entry per image, gathering all of
  // that image's roles — an image can hold several roles in the same group.
  const membersByImage = useMemo<ImageMembers[]>(() => {
    const map = new Map<string, Membership[]>();
    for (const m of membersData?.results ?? []) {
      const list = map.get(m.image_id);
      if (list) list.push(m);
      else map.set(m.image_id, [m]);
    }
    return Array.from(map.entries()).map(([image_id, roles]) => ({ image_id, roles }));
  }, [membersData]);

  // Distinct images per role, for the count badge on each role chip.
  const roleCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const mem of membersByImage) {
      for (const role of new Set(mem.roles.map(r => r.role))) {
        counts.set(role, (counts.get(role) ?? 0) + 1);
      }
    }
    return counts;
  }, [membersByImage]);

  const filteredMembers = useMemo(() => {
    if (roleFilter.length === 0) return membersByImage;
    return membersByImage.filter(mem => mem.roles.some(r => roleFilter.includes(r.role)));
  }, [membersByImage, roleFilter]);

  // Banner image. Pick the SAME image the groups list card shows: the explicit
  // cover_image_id if set, otherwise the earliest member by date_created — this
  // mirrors the backend's resolve_cover_thumbnail / batch_cover_thumbnails. We
  // then render the ORIGINAL full-res image (.image), never the thumbnail.
  const hasCover = Boolean(group?.cover_image_id);
  const coverImageId = useMemo(() => {
    if (group?.cover_image_id) return group.cover_image_id;
    const members = membersData?.results ?? [];
    if (members.length === 0) return undefined;
    return members.reduce((a, b) => (a.date_created <= b.date_created ? a : b)).image_id;
  }, [group?.cover_image_id, membersData]);
  const coverImage = (coverImageId && imagesById.get(coverImageId)) || previewData?.results?.[0];
  const coverUrl = coverImage?.image;

  return (
    <MainContainer isDrawerOpen={false}>
      {/* Full-bleed cover banner, like the dataset detail hero. Always visible
          (independent of the metadata toggle). Only labelled "Main image" when
          an explicit cover is set — otherwise it's just a representative preview. */}
      {!isLoading && group && coverUrl && (
        <div className="relative shrink-0 w-full h-40 sm:h-44 md:h-52 bg-black/5 dark:bg-white/5 overflow-hidden">
          <div
            className="absolute inset-0 bg-cover bg-center scale-110 blur-2xl opacity-40"
            style={{ backgroundImage: `url(${coverUrl})` }}
          />
          <img src={coverUrl} alt="" className="relative w-full h-full object-contain" />
          {hasCover && (
            <span className="absolute bottom-4 right-4 px-3 py-1 rounded-full bg-black/60 text-white text-xs font-medium">
              Main image
            </span>
          )}
        </div>
      )}
      <div className="p-3 sm:p-6 max-w-5xl mx-auto w-full">
        {isLoading || !group ? (
          <div className="flex flex-col gap-3">
            <LoaderSkeleton className="h-8 w-1/2" />
            <LoaderSkeleton className="h-4 w-1/3" />
            <LoaderSkeleton className="h-24 w-full" />
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            <Link
              to={URLS.GROUP_LIST()}
              className="flex items-center gap-1 text-xs sm:text-sm opacity-40 hover:opacity-100 w-fit"
            >
              <ArrowLeftIcon className="w-3 h-3" />
              Groups
            </Link>

            <header className="flex flex-col gap-2">
              <div className="flex flex-row gap-2 items-center flex-wrap">
                <h1 className="text-2xl font-bold leading-tight">{group.name}</h1>
                <span className="text-[10px] font-medium uppercase px-1.5 py-0.5 rounded-full bg-black/10 dark:bg-white/10">
                  {group.type}
                </span>
              </div>
              <p className="text-xs opacity-50 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <Link to={URLS.IMAGE_LIST(allMembersParams)} className="hover:underline">
                  {formatNumber(group.image_count, { decimals: 0 })} images
                </Link>
                {group.author?.email && <span>&middot; by {group.author.email}</span>}
                <span title={group.date_created}>
                  &middot; Created {new Date(group.date_created).toLocaleDateString()}
                </span>
                {group.date_updated !== group.date_created && (
                  <span title={group.date_updated}>
                    &middot; Updated {new Date(group.date_updated).toLocaleDateString()}
                  </span>
                )}
              </p>
              {group.description && <TextToParagraphs text={group.description} className="text-sm opacity-80" />}
              <p className="text-[11px] opacity-30 truncate font-mono">{group.id}</p>
            </header>

            {/* Members take the main column; type/roles/metadata live in a
                narrow rail on the right (stacks below on small screens). */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_17rem] gap-6 items-start">
              <section className="flex flex-col gap-3 min-w-0">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold uppercase tracking-wide opacity-60">Members</h2>
                    {roleFilter.length > 0 && (
                      <span className="text-xs opacity-60">
                        {filteredMembers.length} of {membersByImage.length}
                        <button
                          type="button"
                          onClick={() => setRoleFilter([])}
                          className="ml-2 text-brand-500 hover:underline cursor-pointer"
                        >
                          Clear filter
                        </button>
                      </span>
                    )}
                  </div>
                  <div className="flex items-center rounded-md border border-black/10 dark:border-white/10 p-0.5">
                    <button
                      type="button"
                      onClick={() => setMemberView("comfortable")}
                      title="Comfortable view"
                      className={twMerge(
                        "p-1 rounded cursor-pointer transition-colors",
                        memberView === "comfortable" ? "bg-black/10 dark:bg-white/10" : "opacity-50 hover:opacity-100"
                      )}
                    >
                      <ListBulletIcon className="size-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setMemberView("compact")}
                      title="Compact grid"
                      className={twMerge(
                        "p-1 rounded cursor-pointer transition-colors",
                        memberView === "compact" ? "bg-black/10 dark:bg-white/10" : "opacity-50 hover:opacity-100"
                      )}
                    >
                      <Squares2X2Icon className="size-4" />
                    </button>
                  </div>
                </div>
                {(isLoadingPreview || isLoadingMembers) && membersByImage.length === 0 ? (
                  <div className="flex flex-col gap-2">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <LoaderSkeleton key={i} className="h-36 sm:h-40 rounded-lg" />
                    ))}
                  </div>
                ) : membersByImage.length === 0 ? (
                  <p className="text-sm opacity-50">No members yet.</p>
                ) : filteredMembers.length === 0 ? (
                  <p className="text-sm opacity-50">No members match the selected roles.</p>
                ) : memberView === "compact" ? (
                  <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-[70vh] overflow-y-auto overflow-x-hidden p-1">
                    {filteredMembers.map(mem => (
                      <MemberTile
                        key={mem.image_id}
                        member={mem}
                        image={imagesById.get(mem.image_id)}
                        isCover={hasCover && mem.image_id === group.cover_image_id}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col gap-2 max-h-[70vh] overflow-y-auto overflow-x-hidden pl-1 pr-6 py-1 max-w-xl">
                    {filteredMembers.map(mem => (
                      <MemberRow
                        key={mem.image_id}
                        member={mem}
                        image={imagesById.get(mem.image_id)}
                        isCover={hasCover && mem.image_id === group.cover_image_id}
                      />
                    ))}
                  </div>
                )}
                {group.image_count > 0 && (
                  <Link
                    to={URLS.IMAGE_LIST(allMembersParams)}
                    className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:underline w-fit"
                  >
                    View members in images view &rarr;
                  </Link>
                )}
              </section>

              <aside className="flex flex-col gap-5 lg:sticky lg:top-4">
                <section className="flex flex-col gap-2">
                  <h2 className="text-sm font-bold uppercase tracking-wide opacity-60">Roles</h2>
                  {!groupType ? (
                    <LoaderSkeleton className="h-6 w-1/3" />
                  ) : (groupType.roles ?? []).length === 0 ? (
                    <p className="text-sm opacity-50">No roles defined on this group type.</p>
                  ) : (
                    <div className="flex flex-row flex-wrap gap-2">
                      {(groupType.roles ?? []).map(r => {
                        const active = roleFilter.includes(r.role);
                        const count = roleCounts.get(r.role) ?? 0;
                        return (
                          <button
                            key={r.role}
                            type="button"
                            onClick={() => toggleRoleFilter(r.role)}
                            title={
                              r.is_required
                                ? "Required role — click to filter members"
                                : "Click to filter members by this role"
                            }
                            className={twMerge(
                              "text-xs font-medium px-2 py-1 rounded-full transition-colors cursor-pointer inline-flex items-center gap-1.5",
                              active
                                ? "bg-brand-500 text-white"
                                : r.is_required
                                  ? "bg-brand-500/20 text-brand-700 dark:text-brand-300 hover:bg-brand-500/30"
                                  : "bg-black/5 dark:bg-white/10 text-black/45 dark:text-white/55 hover:bg-black/10 dark:hover:bg-white/20"
                            )}
                          >
                            {r.role}
                            {r.is_required && <span className="opacity-70">*</span>}
                            <span className={twMerge("text-[10px]", active ? "opacity-80" : "opacity-50")}>
                              {count}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </section>

                {group.metadata && Object.keys(group.metadata).length > 0 && (
                  <GroupMetadataPanel metadata={group.metadata} />
                )}
              </aside>
            </div>
          </div>
        )}
      </div>
    </MainContainer>
  );
};
