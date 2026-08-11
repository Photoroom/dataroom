import React, { createContext, useCallback, useContext, useState } from "react";

const STORAGE_KEY = "filterSidebar";
const DEFAULT_SECTIONS = ["source", "tag", "dataset"];
// Sections that can't be removed — the dataset filter is always available.
const PINNED_SECTIONS = ["dataset"];

export const isPinnedSection = (field: string) => PINNED_SECTIONS.includes(field);

const DEFAULT_WIDTH = 240; // matches the old fixed w-60
const MIN_WIDTH = 200;
const MAX_WIDTH = 480;
const clampWidth = (w: number) => Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(w)));

interface SidebarConfig {
  visible: boolean;
  sections: string[];
  collapsed: Record<string, boolean>;
  width: number;
}

// Pinned sections are re-added even if an older stored config removed them.
const withPinned = (sections: string[]) => [...sections, ...PINNED_SECTIONS.filter(p => !sections.includes(p))];

function loadConfig(): SidebarConfig {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        visible: parsed.visible ?? true,
        sections: withPinned(Array.isArray(parsed.sections) ? parsed.sections : DEFAULT_SECTIONS),
        collapsed: parsed.collapsed ?? {},
        width: clampWidth(Number(parsed.width) || DEFAULT_WIDTH),
      };
    }
  } catch {
    // ignore parse errors
  }
  return { visible: true, sections: [...DEFAULT_SECTIONS], collapsed: {}, width: DEFAULT_WIDTH };
}

function saveConfig(config: SidebarConfig) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

interface SidebarConfigContextType {
  isVisible: boolean;
  sections: string[];
  collapsed: Record<string, boolean>;
  width: number;
  toggleVisible: () => void;
  addSection: (field: string) => void;
  removeSection: (field: string) => void;
  toggleCollapsed: (field: string) => void;
  setWidth: (width: number) => void;
}

const SidebarConfigContext = createContext<SidebarConfigContextType | null>(null);

export function SidebarConfigProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<SidebarConfig>(loadConfig);

  const update = useCallback((fn: (prev: SidebarConfig) => SidebarConfig) => {
    setConfig(prev => {
      const next = fn(prev);
      saveConfig(next);
      return next;
    });
  }, []);

  const toggleVisible = useCallback(() => update(c => ({ ...c, visible: !c.visible })), [update]);

  const addSection = useCallback(
    (field: string) =>
      update(c => ({
        ...c,
        sections: c.sections.includes(field) ? c.sections : [...c.sections, field],
      })),
    [update]
  );

  const removeSection = useCallback(
    (field: string) =>
      update(c =>
        isPinnedSection(field)
          ? c
          : {
              ...c,
              sections: c.sections.filter(s => s !== field),
            }
      ),
    [update]
  );

  const setWidth = useCallback((width: number) => update(c => ({ ...c, width: clampWidth(width) })), [update]);

  const toggleCollapsed = useCallback(
    (field: string) =>
      update(c => ({
        ...c,
        collapsed: { ...c.collapsed, [field]: !c.collapsed[field] },
      })),
    [update]
  );

  return (
    <SidebarConfigContext.Provider
      value={{
        isVisible: config.visible,
        sections: config.sections,
        collapsed: config.collapsed,
        width: config.width,
        toggleVisible,
        addSection,
        removeSection,
        toggleCollapsed,
        setWidth,
      }}
    >
      {children}
    </SidebarConfigContext.Provider>
  );
}

export function useSidebarConfig() {
  const ctx = useContext(SidebarConfigContext);
  if (!ctx) throw new Error("useSidebarConfig must be used within SidebarConfigProvider");
  return ctx;
}
