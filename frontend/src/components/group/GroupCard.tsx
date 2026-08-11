import React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckIcon } from "@heroicons/react/20/solid";
import { twMerge } from "tailwind-merge";
import { Group } from "../../api/client.schemas";
import { formatNumber } from "../../utils/formatNumber";
import { URLS } from "../../urls";
import { useGroupSelection } from "../../context/GroupSelectionContext";

interface GroupCardProps {
  group: Group;
}

export const GroupCard: React.FC<GroupCardProps> = function ({ group }) {
  // cover_thumbnail is batched server-side (GroupViewSet.list)
  const coverSrc = group.cover_thumbnail || undefined;

  const { isSelecting, selectedGroupIds, selectionType, toggleSelectedGroup } = useGroupSelection();
  const isSelected = selectedGroupIds.includes(group.id);
  // other types can't join once one's locked
  const isOtherType = isSelecting && selectionType !== null && group.type !== selectionType;

  // open the drawer via ?group=, keeping the list filters
  const [searchParams] = useSearchParams();
  const drawerParams = new URLSearchParams(searchParams);
  drawerParams.set("group", group.id);

  const inner = (
    <div className="relative w-full aspect-square overflow-hidden bg-black/8 dark:bg-white/8">
      {coverSrc ? (
        <img
          src={coverSrc}
          alt=""
          loading="lazy"
          className="block w-full h-full object-cover transition-transform group-hover:scale-[102%]"
        />
      ) : (
        <div className="flex items-center justify-center w-full h-full text-xs opacity-30">No images</div>
      )}
      <span className="absolute top-1.5 left-1.5 max-w-[calc(100%-0.75rem)] truncate rounded-full bg-black/30 text-white/90 text-[11px] font-medium tracking-wide px-2 py-0.5">
        {group.type}
      </span>
      {isSelecting && isSelected && (
        <span className="absolute z-10 bottom-1.5 left-1.5 flex items-center justify-center rounded-full w-7 h-7 bg-brand-400 shadow-sm">
          <CheckIcon className="size-4 text-white" />
        </span>
      )}
    </div>
  );

  const footer = (
    <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs">
      <span className="truncate font-medium" title={group.name}>
        {group.name}
      </span>
      <span className="shrink-0 tabular-nums opacity-60">{formatNumber(group.image_count, { decimals: 0 })}</span>
    </div>
  );

  const cardClasses = twMerge(
    "group block w-full text-left rounded-lg overflow-hidden bg-black/4 dark:bg-white/4 ring-1 transition-colors",
    isSelecting && isSelected
      ? "ring-2 ring-brand-400"
      : "ring-black/8 dark:ring-white/8 hover:ring-black/15 dark:hover:ring-white/15"
  );

  if (isSelecting) {
    return (
      <button
        type="button"
        data-group-id={group.id}
        disabled={isOtherType}
        title={isOtherType ? `Different type (${group.type})` : group.name}
        onClick={e => toggleSelectedGroup(group, e.shiftKey)}
        className={twMerge(
          cardClasses,
          "cursor-pointer select-none",
          isOtherType && "opacity-40 grayscale cursor-not-allowed"
        )}
      >
        {inner}
        {footer}
      </button>
    );
  }

  return (
    <Link data-group-id={group.id} to={URLS.GROUP_LIST(drawerParams)} title={group.name} className={cardClasses}>
      {inner}
      {footer}
    </Link>
  );
};
