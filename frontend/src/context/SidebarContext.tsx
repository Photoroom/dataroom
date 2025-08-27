import React, { createContext, useContext, useEffect, useState } from "react";

export enum SidebarActiveNav {
  IMAGES = "images",
  DATASETS = "datasets",
  SETTINGS = "settings",
  ADMIN = "admin",
}

interface SidebarContextType {
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  isSidebarNavOpen: boolean;
  setIsSidebarNavOpen: (open: boolean) => void;
  sidebarActiveNav: SidebarActiveNav;
  setSidebarActiveNav: (nav: SidebarActiveNav) => void;
}

const SidebarContext = createContext<SidebarContextType | undefined>(undefined);

export function SidebarProvider({
  initialActiveNav,
  children,
}: {
  initialActiveNav: SidebarActiveNav;
  children: React.ReactNode;
}) {
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(() => {
    const cookies = document.cookie.split(";");
    const sidebarCookie = cookies.find(cookie => cookie.trim().startsWith("sidebar="));
    return sidebarCookie ? sidebarCookie.split("=")[1].trim() === "open" : false;
  });
  const [isSidebarNavOpen, setIsSidebarNavOpen] = useState<boolean>(false);
  const [sidebarActiveNav, setSidebarActiveNav] = useState<SidebarActiveNav>(initialActiveNav);

  useEffect(() => {
    // Update cookie when sidebar state changes
    document.cookie = `sidebar=${isSidebarOpen ? "open" : "closed"}; path=/; max-age=31536000`;
  }, [isSidebarOpen]);

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
  };

  return (
    <SidebarContext.Provider
      value={{
        isSidebarOpen,
        toggleSidebar,
        isSidebarNavOpen,
        setIsSidebarNavOpen,
        sidebarActiveNav,
        setSidebarActiveNav,
      }}
    >
      {children}
    </SidebarContext.Provider>
  );
}

// hook to use the sidebar context
export function useSidebar() {
  const context = useContext(SidebarContext);
  if (context === undefined) {
    throw new Error("useSidebar must be used within a SidebarProvider");
  }
  return context;
}
