import React, { createContext, useContext, useState } from 'react';

interface CollapsibleContextType {
  toggleCollapsible: (name: string) => void;
  setCollapsibleState: (name: string, isOpen: boolean) => void;
  getCollapsibleState: (name: string, defaultValue: boolean) => boolean;
}

const CollapsibleContext = createContext<CollapsibleContextType | undefined>(undefined);

// Cookie helpers
const getCookieValue = (name: string): boolean | null => {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(^| )collapsible-${name}=([^;]+)`));
  return match ? match[2] === 'open' : null;
};

const setCookie = (name: string, value: boolean): void => {
  document.cookie = `collapsible-${name}=${value ? 'open' : 'closed'}; path=/; max-age=31536000`;
};

export function CollapsibleProvider({ children }: { children: React.ReactNode }) {
  // We'll use this to cache values we've already read from cookies
  const [cache, setCache] = useState<Record<string, boolean>>({});

  const getCollapsibleState = (name: string, defaultValue: boolean): boolean => {
    // Check cache first
    if (name in cache) {
      return cache[name];
    }
    
    // Check cookie
    const cookieValue = getCookieValue(name);
    
    // Return cookie value or default
    return cookieValue !== null ? cookieValue : defaultValue;
  };

  const setCollapsibleState = (name: string, isOpen: boolean) => {
    // Update cookie
    setCookie(name, isOpen);
    
    // Update cache
    setCache(prev => ({
      ...prev,
      [name]: isOpen
    }));
  };

  const toggleCollapsible = (name: string) => {
    const currentValue = getCollapsibleState(name, true);
    setCollapsibleState(name, !currentValue);
  };

  return (
    <CollapsibleContext.Provider value={{
      toggleCollapsible,
      setCollapsibleState,
      getCollapsibleState,
    }}>
      {children}
    </CollapsibleContext.Provider>
  );
}

// Hook to use the collapsible context
export function useCollapsible() {
  const context = useContext(CollapsibleContext);
  if (context === undefined) {
    throw new Error('useCollapsible must be used within a CollapsibleProvider');
  }
  return context;
} 
