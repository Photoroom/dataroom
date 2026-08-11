import React from "react";
import { Link } from "react-router-dom";
import { Group, OSImage } from "../../api/client.schemas";
import { useImagesGroupsRetrieve } from "../../api/client";
import { Collapsible } from "../common/Collapsible";
import { LoaderSkeleton } from "../common/LoaderSkeleton";
import { URLS } from "../../urls";

interface ImageMembershipsProps {
  image?: OSImage;
}

// /api/images/{id}/groups/ returns hydrated groups (the OS denorm array only
// has the type + uuid, not the group name). The endpoint has no response
// schema, so the orval hook types it as void — declare the shape here.
interface ImageGroupMembership {
  group: Group;
  role: string;
  metadata: Record<string, unknown>;
}

export const ImageMemberships: React.FC<ImageMembershipsProps> = ({ image }) => {
  const { data, isLoading } = useImagesGroupsRetrieve<ImageGroupMembership[]>(image?.id ?? "", {
    query: { enabled: Boolean(image?.id) },
  });

  if (!image || isLoading) {
    return (
      <Collapsible name="memberships" title="Groups">
        <div className="flex flex-row flex-wrap items-center gap-2">
          <LoaderSkeleton className="w-24" />
          <LoaderSkeleton className="w-24" />
        </div>
      </Collapsible>
    );
  }

  const memberships = data ?? [];

  return (
    <Collapsible name="memberships" title="Groups">
      <div className="flex flex-col gap-1.5">
        {memberships.length === 0 && <p className="opacity-50">No group memberships</p>}
        {memberships.map((m, i) => (
          <div key={`${m.group.id}-${m.role}-${i}`} className="flex flex-row items-center gap-2 text-xs">
            <Link
              to={URLS.GROUP_DETAIL(m.group.id)}
              title={`Open group ${m.group.name}`}
              className="px-2 py-0.5 rounded-full bg-black/8 dark:bg-white/8 hover:bg-black/15 dark:hover:bg-white/15 transition-colors"
            >
              <span className="font-medium">{m.role}</span>
              <span className="opacity-50"> in </span>
              <span>{m.group.name}</span>
            </Link>
            <span className="opacity-40 text-[10px] uppercase tracking-wide">{m.group.type}</span>
          </div>
        ))}
      </div>
    </Collapsible>
  );
};
