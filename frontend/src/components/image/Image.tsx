import React, { useMemo, useState, useCallback } from "react";
import { OSImage, SimilarOSImage } from "../../api/client.schemas";
import { ArrowsRightLeftIcon, CheckIcon } from "@heroicons/react/20/solid";
import { twMerge } from "tailwind-merge";
import { useNavigate, useSearchParams } from "react-router-dom";
import { URLS } from "../../urls";
import { useImageListData } from "../../context/ImageListDataContext";

interface ImageProps {
  image: OSImage | SimilarOSImage;
  selectMode?: boolean;
  isSelected?: boolean;
  onToggleSelected?: (isMultiSelect: boolean) => void;
  className?: string;
  label?: string;
}

export const Image: React.FC<ImageProps> = ({ image, selectMode, isSelected, onToggleSelected, className, label }) => {
  const [searchParams] = useSearchParams();
  const { setModeSimilarImage } = useImageListData();
  const navigate = useNavigate();

  const handleToggleSelected = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (onToggleSelected) {
      const isMultiSelect = event.shiftKey;
      onToggleSelected(isMultiSelect);
    }
  };

  const handleClickSimilar = () => {
    setModeSimilarImage(image.id);
  };

  const props = (() => {
    if (selectMode) {
      return {
        onClick: handleToggleSelected,
      };
    } else if ((image as SimilarOSImage).similarity) {
      return {
        onClick: handleClickSimilar,
      };
    } else {
      return {
        onClick: () => {
          navigate(URLS.IMAGE_DETAIL(image.id, searchParams));
        },
      };
    }
  })();

  const sources = useMemo(
    () => Array.from(new Set([image.thumbnail, image.image].filter((src): src is string => Boolean(src)))),
    [image]
  );

  const [idx, setIdx] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const maxAttemptsPerSource = 2;

  const src = sources[idx];

  const onError = useCallback(() => {
    if (import.meta.env?.DEV) {
      console.warn("[tile] load error", {
        id: image.id,
        src,
        idx,
        attempt,
      });
    }
    if (attempt + 1 < maxAttemptsPerSource) {
      setAttempt(attempt + 1);
    } else if (idx + 1 < sources.length) {
      setIdx(idx + 1);
      setAttempt(0);
    }
    // else give up silently for this tile; leaving a blank is acceptable fallback
  }, [attempt, idx, src, sources.length]);

  return (
    <button {...props} className={twMerge("w-full aspect-square rounded-lg bg-black/8 dark:bg-white/8", className)}>
      <div className={twMerge("group block w-full h-full cursor-pointer relative")}>
        {selectMode && isSelected && (
          <span className="absolute z-10 bottom-2 left-2 flex items-center justify-center rounded-full w-[28px] h-[28px] shadow-sm bg-teal-400">
            <CheckIcon className="size-4 text-white block" />
          </span>
        )}
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          fetchPriority="low"
          onError={onError}
          className={twMerge(
            "block w-full h-full rounded-lg object-cover shadow-none group-hover:shadow-md group-hover:scale-[102%] transition-all",
            selectMode && isSelected ? "ring-4 ring-teal-400" : ""
          )}
        />
        <span>
          {(image as SimilarOSImage).similarity ? (
            <span
              className={twMerge(
                "flex flex-row items-center gap-1",
                "absolute bottom-0 left-0 right-0 overflow-hidden",
                "bg-gradient-to-t from-black/70 to-black/0",
                "text-white font-normal text-xs px-1 p-1 rounded-b-lg text-left"
              )}
            >
              <ArrowsRightLeftIcon className="size-3 shrink-0" />
              <span>{(image as SimilarOSImage).similarity}</span>
            </span>
          ) : (
            <>
              {label && (
                <span
                  className={twMerge(
                    "block absolute bottom-0 left-0 right-0 overflow-hidden",
                    "bg-gradient-to-t from-black/70 to-black/0",
                    "text-white font-normal text-xs px-1 p-1 rounded-b-lg text-left break-all"
                  )}
                >
                  {label}
                </span>
              )}
            </>
          )}
        </span>
      </div>
    </button>
  );
};
