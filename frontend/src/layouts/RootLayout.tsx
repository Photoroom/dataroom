import React from "react";
import { Outlet } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { ThemeProvider } from "../context/ThemeContext";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      gcTime: 30_000, // keep cached data for 30s after last observer unmounts
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    },
  },
});

export function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <Toaster toastOptions={{ className: "text-sm" }} />
        <Outlet />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
