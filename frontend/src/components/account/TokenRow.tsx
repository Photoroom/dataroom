import React, { useState } from "react";
import { twMerge } from "tailwind-merge";
import { EyeIcon, EyeSlashIcon, TrashIcon, ClipboardDocumentIcon } from "@heroicons/react/24/outline";
import { useTokensDestroy, useTokensUpdate } from "../../api/client";
import { ToggleButton } from "../forms/ToggleButton";
import { Token } from "../../api/client.schemas";
import { toast } from "react-hot-toast";

export const TokenRow: React.FC<{ token: Token; refetchTokens: () => void }> = ({ token, refetchTokens }) => {
  const [isVisible, setIsVisible] = useState(false);
  const { mutate: deleteToken } = useTokensDestroy();
  const { mutate: updateToken, isPending: isUpdatingToken } = useTokensUpdate();

  const iconBtn =
    "p-1 rounded opacity-50 hover:opacity-100 cursor-pointer hover:bg-black/5 dark:hover:bg-white/5 transition-colors shrink-0";

  return (
    <div className="flex flex-col gap-1.5 p-2 rounded-lg bg-black/3 dark:bg-white/3">
      {/* Token value + action icons */}
      <div className="flex items-center gap-1">
        <pre className="flex-1 min-w-0 text-[10px] font-mono truncate select-all">
          {isVisible ? token.key : "••••••••••••••••••••••••••••"}
        </pre>
        <button
          type="button"
          className={iconBtn}
          title={isVisible ? "Hide" : "Show"}
          onClick={() => setIsVisible(!isVisible)}
        >
          {isVisible ? <EyeSlashIcon className="size-3.5" /> : <EyeIcon className="size-3.5" />}
        </button>
        <button
          type="button"
          className={iconBtn}
          title="Copy"
          onClick={() => {
            navigator.clipboard.writeText(token.key);
            toast.success("Token copied");
          }}
        >
          <ClipboardDocumentIcon className="size-3.5" />
        </button>
        <button
          type="button"
          className={twMerge(iconBtn, "hover:text-rose-600")}
          title="Delete"
          onClick={() => {
            if (confirm("Delete this API token?")) {
              deleteToken(
                { id: token.id },
                {
                  onSuccess: () => {
                    refetchTokens();
                    toast.success("Token deleted");
                  },
                  onError: () => toast.error("Failed to delete token"),
                }
              );
            }
          }}
        >
          <TrashIcon className="size-3.5" />
        </button>
      </div>
      {/* Read-only toggle */}
      <div className="flex items-center">
        <ToggleButton
          label="Read-only"
          checked={token.is_readonly}
          onChange={checked => {
            updateToken(
              { id: token.id, data: { is_readonly: checked } },
              {
                onSuccess: () => {
                  refetchTokens();
                  toast.success("Token updated");
                },
                onError: () => toast.error("Failed to update token"),
              }
            );
          }}
          disabled={isUpdatingToken}
        />
      </div>
    </div>
  );
};
