import React from "react";
import { Link } from "react-router-dom";
import { Card } from "../common/Card";
import { GroupType } from "../../api/client.schemas";
import { TextToParagraphs } from "../common/TextToParagraphs";
import { formatNumber } from "../../utils/formatNumber";
import { URLS } from "../../urls";

interface GroupTypeCardProps {
  groupType: GroupType;
}

export const GroupTypeCard: React.FC<GroupTypeCardProps> = function ({ groupType }) {
  const roles = groupType.roles ?? [];
  const count = groupType.group_count ?? 0;
  const groupsParams = new URLSearchParams({ type: groupType.name });

  return (
    <Card key={groupType.name} className="flex-col overflow-hidden">
      <div className="flex flex-col gap-1.5 p-3">
        <h3 className="text-sm font-bold leading-tight break-words">{groupType.name}</h3>
        {groupType.description && (
          <TextToParagraphs text={groupType.description} className="text-[11px] opacity-70 line-clamp-2" />
        )}
        {roles.length > 0 && (
          <div className="flex flex-row flex-wrap gap-1">
            {roles.map(r => (
              <span
                key={r.role}
                title={r.is_required ? "Required role" : "Optional role"}
                className={
                  "text-[10px] font-medium px-1.5 py-0.5 rounded-full " +
                  (r.is_required
                    ? "bg-brand-500/20 text-brand-700 dark:text-brand-300"
                    : "bg-black/5 dark:bg-white/10 text-black/45 dark:text-white/55")
                }
              >
                {r.role}
                {r.is_required && <span className="ml-0.5 opacity-70">*</span>}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 px-3 py-2 border-t border-black/5 dark:border-white/10">
        {count > 0 ? (
          <Link
            to={URLS.GROUP_LIST(groupsParams)}
            className="text-xs font-medium text-brand-600 dark:text-brand-300 hover:underline"
            title={`View groups of type ${groupType.name}`}
          >
            {formatNumber(count, { decimals: 0 })} {count === 1 ? "group" : "groups"} &rarr;
          </Link>
        ) : (
          <span className="text-xs opacity-40">No groups</span>
        )}
        <span className="text-[10px] opacity-40 shrink-0" title={`Created ${groupType.date_created}`}>
          {new Date(groupType.date_created).toLocaleDateString()}
        </span>
      </div>
    </Card>
  );
};
