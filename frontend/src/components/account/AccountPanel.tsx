import React from "react";
import ReactDOM from "react-dom";
import { twMerge } from "tailwind-merge";
import {
  XMarkIcon,
  ShieldCheckIcon,
  PlusIcon,
  DocumentTextIcon,
  ArrowRightStartOnRectangleIcon,
} from "@heroicons/react/24/outline";
import { useSettings } from "../../context/SettingsContext";
import { useTokensList, useTokensCreate } from "../../api/client";
import { LoaderSkeleton } from "../common/LoaderSkeleton";
import { ToggleThemeButton } from "../../layouts/sidebar/ToggleThemeButton";
import { TokenRow } from "./TokenRow";
import { toast } from "react-hot-toast";

export const AccountPanel: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const { user, urls } = useSettings();
  const { data: tokens, isLoading: isLoadingTokens, refetch: refetchTokens } = useTokensList();
  const { mutate: createToken, isPending: isCreatingToken } = useTokensCreate();

  const sectionClass = "px-5 py-4 border-b border-light-200 dark:border-dark-300";

  const linkClass =
    "flex items-center gap-2.5 py-2 px-1 text-sm rounded-md hover:bg-black/5 dark:hover:bg-white/5 transition-colors opacity-70 hover:opacity-100";

  return ReactDOM.createPortal(
    <div
      className={twMerge(
        // Mobile: bottom sheet half screen
        "fixed z-50 bottom-0 left-0 right-0 h-1/2",
        "rounded-t-xl border-t",
        // Desktop: right side panel
        "sm:left-auto sm:top-14 sm:h-auto sm:w-[26rem] sm:rounded-t-none sm:rounded-l-xl sm:border-t-0 sm:border-l",
        "bg-light-100 dark:bg-dark-100",
        "border-light-300 dark:border-dark-300",
        "shadow-xl flex flex-col"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-light-200 dark:border-dark-300 shrink-0">
        <span className="text-sm font-semibold">Account</span>
        <button type="button" onClick={onClose} className="opacity-50 hover:opacity-100 cursor-pointer">
          <XMarkIcon className="size-4" />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {/* User info */}
        <div className={twMerge(sectionClass, "flex items-center justify-between")}>
          <div>
            <p className="text-[10px] opacity-40 mb-0.5">Email</p>
            <p className="text-sm">{user.email}</p>
          </div>
          <ToggleThemeButton size="lg" />
        </div>

        {/* API Tokens */}
        <div className={sectionClass}>
          <p className="text-[10px] opacity-40 mb-2">API Tokens</p>
          <div className="flex flex-col gap-1.5">
            {isLoadingTokens && <LoaderSkeleton className="h-10" />}
            {tokens?.results.map(token => <TokenRow key={token.id} token={token} refetchTokens={refetchTokens} />)}
            <button
              type="button"
              className="btn btn-outline btn-sm shrink-0 self-start mt-1"
              onClick={() => {
                createToken(
                  { data: { is_readonly: false } },
                  {
                    onSuccess: () => {
                      refetchTokens();
                      toast.success("Token created");
                    },
                    onError: () => toast.error("Failed to create token"),
                  }
                );
              }}
              disabled={isCreatingToken}
            >
              <PlusIcon />
              <span>Create token</span>
            </button>
          </div>
        </div>

        {/* Links */}
        <div className={sectionClass}>
          <div className="flex flex-col">
            {user.isStaff && urls.adminBackend && (
              <a href={urls.adminBackend} className={linkClass}>
                <ShieldCheckIcon className="size-4 shrink-0" />
                Admin Backend
              </a>
            )}
            <a href={urls.APIdocs} className={linkClass}>
              <DocumentTextIcon className="size-4 shrink-0" />
              API Documentation
            </a>
          </div>
        </div>
      </div>

      {/* Footer: version + logout */}
      <div className="shrink-0 px-5 py-3 border-t border-light-200 dark:border-dark-300 flex items-center justify-between">
        {/* eslint-disable no-undef */}
        <a
          href={`${__GIT_REPO_URL__}/commit/${__GIT_COMMIT__}`}
          target="_blank"
          rel="noreferrer"
          className="text-[10px] font-mono opacity-25 hover:opacity-50 transition-opacity"
          title={__GIT_COMMIT__}
        >
          {__GIT_COMMIT__?.substring(0, 7) || "dev"}
        </a>
        {/* eslint-enable no-undef */}
        <a
          href={urls.logout}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs opacity-60 hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
        >
          <ArrowRightStartOnRectangleIcon className="size-4" />
          Log out
        </a>
      </div>
    </div>,
    document.body
  );
};
