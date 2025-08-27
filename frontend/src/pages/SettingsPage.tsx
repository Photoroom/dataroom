import React, { useState } from "react";
import { useSettings } from "../context/SettingsContext";
import { ChevronRightIcon, EyeIcon, EyeSlashIcon, PlusIcon, TrashIcon } from "@heroicons/react/24/outline";
import { twMerge } from "tailwind-merge";
import { ToggleThemeButton } from "../layouts/sidebar/ToggleThemeButton";
import { useTokensList, useTokensCreate, useTokensDestroy, useTokensUpdate } from "../api/client";
import { LoaderSkeleton } from "../components/common/LoaderSkeleton";
import { toast } from "react-hot-toast";
import { ToggleButton } from "../components/forms/ToggleButton";
import { Token } from "../api/client.schemas";

interface MenuLinkProps {
  href: string;
  children: React.ReactNode;
}

const MenuLink: React.FC<MenuLinkProps> = ({ href, children }) => (
  <p>
    <a href={href} className="group my-2 inline-block align-middle" role="menuitem">
      <ChevronRightIcon className="size-4 inline-block mr-1" />
      <span className="inline-block group-hover:underline">{children}</span>
    </a>
  </p>
);

interface TokenFormProps {
  token: Token;
  refetchTokens: () => void;
}

const TokenForm: React.FC<TokenFormProps> = ({ token, refetchTokens }) => {
  const [isVisible, setIsVisible] = useState(false);
  const { mutate: deleteToken } = useTokensDestroy();
  const { mutate: updateToken, isPending: isUpdatingToken } = useTokensUpdate();

  const handleDeleteToken = () => {
    if (confirm("Are you sure you want to delete this API token?")) {
      deleteToken(
        { id: token.id },
        {
          onSuccess: () => {
            refetchTokens();
            toast.success("API token deleted");
          },
          onError: () => {
            toast.error("Failed to delete API token");
          },
        }
      );
    }
  };

  const handleChangeReadOnly = (checked: boolean) => {
    updateToken(
      { id: token.id, data: { is_readonly: checked } },
      {
        onSuccess: () => {
          refetchTokens();
          toast.success("API token updated");
        },
        onError: () => {
          toast.error("Failed to update API token");
        },
      }
    );
  };

  return (
    <div className="flex flex-row gap-2 items-center justify-start">
      <pre className="py-2 px-3 border border-black/20 dark:border-white/20 rounded-lg text-xs overflow-hidden py-[10px] w-[316px]">
        {isVisible ? token.key : "••••••••••••••••••••••••••••••••••••••••"}
      </pre>
      <button
        type="button"
        className="btn btn-outline btn-icon btn-sm shrink-0"
        title={isVisible ? "Hide token" : "Show token"}
        onClick={() => setIsVisible(!isVisible)}
      >
        {isVisible ? <EyeSlashIcon /> : <EyeIcon />}
      </button>
      <button
        type="button"
        className="btn btn-outline btn-icon btn-sm shrink-0"
        title="Delete token"
        onClick={handleDeleteToken}
      >
        <TrashIcon />
      </button>
      <ToggleButton
        label="Read-only"
        checked={token.is_readonly}
        onChange={handleChangeReadOnly}
        disabled={isUpdatingToken}
      />
    </div>
  );
};

export const SettingsPage: React.FC = function () {
  const { user, urls } = useSettings();

  const { data: tokens, isLoading: isLoadingTokens, refetch: refetchTokens } = useTokensList();
  const { mutate: createToken, isPending: isCreatingToken } = useTokensCreate();

  const handleCreateToken = () => {
    createToken(
      {
        data: {
          is_readonly: false,
        },
      },
      {
        onSuccess: () => {
          refetchTokens();
          toast.success("API token created");
        },
        onError: () => {
          toast.error("Failed to create API token");
        },
      }
    );
  };

  const cardClass =
    "mx-3 p-8 rounded-lg shadow-lg border border-light-300 dark:border-dark-300 bg-light-100 dark:bg-dark-100 flex flex-col gap-2";

  return (
    <div className="flex flex-col gap-4">
      <div className={twMerge(cardClass, "grid grid-cols-2 gap-6")}>
        <div className="">
          <p className="text-sm opacity-70">Email</p>
          <p>{user.email}</p>
        </div>
        <div className="self-center justify-self-end">
          <ToggleThemeButton size="lg" />
        </div>
      </div>
      <div className={cardClass}>
        <p className="text-sm opacity-70 mb-1">API Tokens</p>
        <div className="flex flex-col gap-2">
          {isLoadingTokens && <LoaderSkeleton className="h-10" />}
          {tokens?.results.map(token => (
            <TokenForm key={token.id} token={token} refetchTokens={refetchTokens} />
          ))}
          <button
            type="button"
            className="btn btn-outline btn-sm shrink-0 self-start"
            onClick={handleCreateToken}
            disabled={isCreatingToken}
          >
            <PlusIcon />
            <span>Create token</span>
          </button>
        </div>
      </div>

      <div className={cardClass}>
        <p className="text-sm opacity-70">Links</p>
        <div className="">
          {user.isStaff && urls.adminBackend && <MenuLink href={urls.adminBackend}>Admin Backend</MenuLink>}
          <MenuLink href={urls.APIdocs}>API docs</MenuLink>
          <MenuLink href={urls.logout}>Log out</MenuLink>
        </div>
      </div>
    </div>
  );
};
