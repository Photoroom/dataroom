import React, { useContext } from "react";

export const SettingsContext = React.createContext({});

export type SettingsContextProps = {
  user: {
    name: string;
    email: string;
    isStaff: boolean;
  };
  urls: {
    adminBackend?: string;
    logout: string;
    login: string;
    APIdocs: string;
    deepscatter: string;
  };
};

export function useSettings(): SettingsContextProps {
  const context = useContext(SettingsContext);

  if (typeof context === "undefined") {
    throw new Error("useSettings should be used within the SettingsContext provider!");
  }

  return context as SettingsContextProps;
}
