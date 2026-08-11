import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { Group } from "../api/client.schemas";

interface GroupSelectionContextType {
  isSelecting: boolean;
  setIsSelecting: (v: boolean) => void;
  selectedGroupIds: string[];
  selectedGroupObjects: Group[];
  // type of the first pick; datasets hold one type so the rest must match it
  selectionType: string | null;
  toggleSelectedGroup: (group: Group, isMultiSelect?: boolean) => void;
  addSelectedGroups: (groups: Group[]) => void;
  clearSelectedGroups: () => void;
  // list registers its page order so shift-range works
  registerGroups: (groups: Group[]) => void;
}

const GroupSelectionContext = createContext<GroupSelectionContextType | undefined>(undefined);

export function GroupSelectionProvider({ children }: { children: React.ReactNode }) {
  const [isSelecting, setIsSelecting] = useState(false);
  const [selected, setSelected] = useState<Group[]>([]); // insertion order = selection order
  const [lastSelectedId, setLastSelectedId] = useState<string | null>(null);
  const [lastWasUnselected, setLastWasUnselected] = useState(false);

  // visible page, in a ref so toggle can range-select without re-subscribing
  const visibleGroups = useRef<Group[]>([]);
  const registerGroups = useCallback((groups: Group[]) => {
    visibleGroups.current = groups;
  }, []);

  const toggleSelectedGroup = useCallback(
    (group: Group, isMultiSelect = false) => {
      setSelected(prev => {
        const has = (id: string) => prev.some(g => g.id === id);
        const isAlreadySelected = has(group.id);
        // lock to the selection's type, else the clicked group's
        const lockedType = prev.length > 0 ? prev[0].type : group.type;

        if (isMultiSelect && lastSelectedId) {
          const list = visibleGroups.current;
          const lastIdx = list.findIndex(g => g.id === lastSelectedId);
          const curIdx = list.findIndex(g => g.id === group.id);
          if (lastIdx !== -1 && curIdx !== -1) {
            const start = Math.min(lastIdx, curIdx);
            const end = Math.max(lastIdx, curIdx);
            // range stays within the locked type
            const range = list.slice(start, end + 1).filter(g => g.type === lockedType);
            if (lastWasUnselected) {
              const rangeIds = new Set(range.map(g => g.id));
              return prev.filter(g => !rangeIds.has(g.id));
            }
            const merged = [...prev];
            for (const g of range) if (!has(g.id)) merged.push(g);
            return merged;
          }
        }

        if (isAlreadySelected) return prev.filter(g => g.id !== group.id);
        if (prev.length > 0 && group.type !== lockedType) return prev; // can't mix types
        return [...prev, group];
      });
      setLastSelectedId(group.id);
      setLastWasUnselected(selected.some(g => g.id === group.id));
    },
    [lastSelectedId, lastWasUnselected, selected]
  );

  const addSelectedGroups = useCallback((groups: Group[]) => {
    setSelected(prev => {
      const seen = new Set(prev.map(g => g.id));
      const merged = [...prev];
      for (const g of groups) if (!seen.has(g.id)) merged.push(g);
      return merged;
    });
  }, []);

  const clearSelectedGroups = useCallback(() => setSelected([]), []);

  const selectedGroupIds = useMemo(() => selected.map(g => g.id), [selected]);
  const selectionType = selected.length > 0 ? selected[0].type : null;

  const value: GroupSelectionContextType = {
    isSelecting,
    setIsSelecting,
    selectedGroupIds,
    selectedGroupObjects: selected,
    selectionType,
    toggleSelectedGroup,
    addSelectedGroups,
    clearSelectedGroups,
    registerGroups,
  };

  return <GroupSelectionContext.Provider value={value}>{children}</GroupSelectionContext.Provider>;
}

export function useGroupSelection() {
  const context = useContext(GroupSelectionContext);
  if (context === undefined) {
    throw new Error("useGroupSelection must be used within a GroupSelectionProvider");
  }
  return context;
}
