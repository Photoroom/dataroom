import React from "react";
import { OSImage, SimilarOSImage } from "../../api/client.schemas";
import { ArrowsRightLeftIcon, CheckIcon } from "@heroicons/react/20/solid";
import { twMerge } from "tailwind-merge";
import { Link, useSearchParams } from "react-router-dom";
import { URLS } from "../../urls";
import { useImageListData } from "../../context/ImageListDataContext";

interface ImageProps {
  image: OSImage | SimilarOSImage;
  selectMode? : boolean,
  isSelected?: boolean,
  onToggleSelected?: (isMultiSelect: boolean) => void,
  className?: string,
  label?: string,
}

export const Image: React.FC<ImageProps> = ({ image, selectMode, isSelected, onToggleSelected, className, label }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { setModeSimilarImage } = useImageListData();

  const handleToggleSelected = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (onToggleSelected) {
      const isMultiSelect = event.shiftKey;
      onToggleSelected(isMultiSelect);
    }
  }

  const handleClickSimilar = () => {
    setModeSimilarImage(image.id);
  }
  
  const Component = selectMode || (image as SimilarOSImage).similarity ? 'button' : Link;
  const props = (() => {
    if (selectMode) {
      return {
        onClick: handleToggleSelected
      }
    } else if ((image as SimilarOSImage).similarity) {
      return {
        onClick: handleClickSimilar
      }
    } else {
      return {
        to: URLS.IMAGE_DETAIL(image.id, searchParams)
      }
    }
  })() as any;

  return (
    <Component {...props} className={twMerge("w-full aspect-square rounded-lg bg-black/8 dark:bg-white/8", className)}>
      <div className={twMerge("group block w-full h-full cursor-pointer relative")}>
        {
          selectMode && isSelected &&
          <span className="absolute z-10 bottom-2 left-2 flex items-center justify-center rounded-full w-[28px] h-[28px] shadow-sm bg-teal-400">
            <CheckIcon className="size-4 text-white block" />
          </span>
        }
        <span
          style={{backgroundImage: `url('${image.thumbnail || image.image}')`}}
          className={twMerge(
            "block w-full h-full rounded-lg bg-cover bg-center shadow-none group-hover:shadow-md group-hover:scale-[102%] transition-all",
            selectMode && isSelected ? "ring-4 ring-teal-400" : "",
          )}
        >
          {
            (image as SimilarOSImage).similarity ? (
                <span className={twMerge(
                  "flex flex-row items-center gap-1",
                  "absolute bottom-0 left-0 right-0 overflow-hidden",
                  "bg-gradient-to-t from-black/70 to-black/0",
                  "text-white font-normal text-xs px-1 p-1 rounded-b-lg text-left"
                )}>
                  <ArrowsRightLeftIcon className="size-3 shrink-0" />
                  <span>{(image as SimilarOSImage).similarity}</span>
                </span>
              ) : (
                <>
                  {label && <span className={twMerge(
                    "block absolute bottom-0 left-0 right-0 overflow-hidden",
                    "bg-gradient-to-t from-black/70 to-black/0",
                    "text-white font-normal text-xs px-1 p-1 rounded-b-lg text-left break-all"
                  )}>
                    {label}
                  </span>}
                </>
              )
          }
        </span>
      </div>
    </Component>
  );
};
