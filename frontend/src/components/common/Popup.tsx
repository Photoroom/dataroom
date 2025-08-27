import React from "react";
import { twMerge } from "tailwind-merge";
import { CloseButton } from "./CloseButton";

export default function Popup({ onClose, children }: { onClose: () => void; children?: React.ReactNode }) {
  return (
    <div
      className={twMerge(
        "fixed z-40 top-0 left-0 right-0 bottom-0 w-full h-full",
        "flex justify-center items-center",
        "bg-black/50 transition-opacity"
      )}
    >
      <div
        className={twMerge(
          "absolute bottom-0 w-full max-w-[600px] max-h-[82%] overflow-auto",
          "bg-light-100 dark:bg-dark-100 rounded-t-2xl m-0 p-8 transition-all",
          "md:bottom-0 md:left-0 md:right-0 md:top-0 md:w-[600px]",
          "md:m-auto md:overflow-auto md:h-fit",
          "md:p-10 md:rounded-2xl"
        )}
      >
        <CloseButton onClick={onClose} />
        {children}
      </div>
    </div>
  );
}
