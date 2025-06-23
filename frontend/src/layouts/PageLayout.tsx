import React from "react";
import { Link, Outlet } from "react-router-dom";
import { Logo } from "../components/common/Logo";
import { URLS } from "../urls";
import { ChevronLeftIcon } from "@heroicons/react/24/outline";

export const PageLayout: React.FC = () => {
  return (
    <div className="container-sm">
      <header className="pt-1 mb-6 md:pt-6">
        <div className="flex flex-row gap-2 items-center">
          <div className="flex flex-row gap-1 items-center justify-start w-full">
            <Logo />
            <h1 className="text-lg block font-bold">Settings</h1>
          </div>
          <Link to={URLS.IMAGE_LIST()} className="text-sm justify-self-end mr-4 shrink-0 hover:underline"><ChevronLeftIcon className="size-4 inline mr-1" />Back to Images</Link>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
};
