import React, { createContext, useContext, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Group } from "../api/client.schemas";
import { useGroupsRetrieve } from "../api/client";
import toast from "react-hot-toast";

interface GroupDrawerContextType {
  isDrawerOpen: boolean;
  closeDrawer: () => void;
  groupId: string;
  group: Group | undefined;
  refetchGroup: () => void;
}

const GroupDrawerContext = createContext<GroupDrawerContextType | undefined>(undefined);

// The group drawer is driven by the `?group=<id>` query param. This keeps the
// group list mounted behind the drawer (unlike navigating to the full detail
// page) and leaves other list filters (type, roles) untouched.
export function GroupDrawerProvider({ children }: { children: React.ReactNode }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const groupId = searchParams.get("group") || "";
  const isDrawerOpen = !!groupId;

  // Closing just drops the `group` param, preserving the rest of the list filters.
  const closeDrawer = () => {
    setSearchParams(
      prev => {
        const next = new URLSearchParams(prev);
        next.delete("group");
        return next;
      },
      { replace: true }
    );
  };

  // -------------------- Fetching group detail --------------------
  const {
    data: group,
    isError,
    refetch: refetchGroup,
  } = useGroupsRetrieve(groupId, { query: { enabled: isDrawerOpen } });

  useEffect(() => {
    if (isError) {
      toast.error("Error loading group");
    }
  }, [isError]);

  return (
    <GroupDrawerContext.Provider value={{ isDrawerOpen, closeDrawer, groupId, group, refetchGroup }}>
      {children}
    </GroupDrawerContext.Provider>
  );
}

export function useGroupDrawer() {
  const context = useContext(GroupDrawerContext);
  if (context === undefined) {
    throw new Error("useGroupDrawer must be used within a GroupDrawerProvider");
  }
  return context;
}
