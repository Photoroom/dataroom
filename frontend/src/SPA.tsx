import * as React from "react";
import * as ReactDOM from "react-dom/client";
import { SettingsContext, SettingsContextProps } from "./context/SettingsContext";
import { RouterProvider } from "react-router-dom";
import { router } from "./router";

import "../styles/index.css";


declare global {
    interface Window {
        SPA: ({}: SettingsContextProps) => void;
    }
}

window.SPA = function(settings: SettingsContextProps) {
  const SettingsProvider = ({ children }: { children?: React.ReactNode }) => {
    return <SettingsContext.Provider value={settings}>{children}</SettingsContext.Provider>;
  };

  const el = document.getElementById("root");
  if (!el) {
    throw new Error("Could not find element with id 'root'");
  }
  ReactDOM.createRoot(el).render(
    <React.StrictMode>
      <SettingsProvider>
        <RouterProvider router={router}/>
      </SettingsProvider>
    </React.StrictMode>
  );
}
