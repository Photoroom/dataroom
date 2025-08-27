import React, { useEffect, useState } from "react";
import { ImageListMode, useImageListData } from "../../context/ImageListDataContext";
import { FunnelIcon, MagnifyingGlassIcon, SparklesIcon } from "@heroicons/react/24/outline";
import { SquaresPlusIcon } from "@heroicons/react/24/outline";
import { SidebarToggle } from "./../sidebar/SidebarToggle";
import { SelectImagesForm } from "./SelectImagesForm";
import { RandomModeForm } from "./RandomModeForm";
import { SearchForm } from "./SearchForm";
import { Filters } from "./Filters";
export const ImagesSidebarContent: React.FC = function () {
  const { mode, setModeBrowse, setModeRandom, isSelecting, setIsSelecting, filters, setFilters } = useImageListData();

  const [isSearchOpen, setIsSearchOpen] = useState(mode === ImageListMode.SIMILAR);
  const [isFilterOpen, setIsFilterOpen] = useState(() => {
    return Object.values(filters).some(
      value => (Array.isArray(value) && value.length > 0) || (!Array.isArray(value) && value !== null)
    );
  });

  useEffect(() => {
    if (mode === ImageListMode.SIMILAR) {
      setIsSearchOpen(true);
    } else {
      setIsSearchOpen(false);
    }
  }, [mode]);

  const resetFilters = () => {
    setFilters({
      sources: [],
      tags: [],
      aspect_ratio_fraction: null,
      has_attributes: [],
      has_latents: [],
      duplicate_state: null,
      datasets: [],
    });
  };

  return (
    <div className="flex flex-col gap-6 px-4 pt-2 pb-6 max-w-sidebar-open mx-auto">
      <SidebarToggle
        icon={SquaresPlusIcon}
        label="Select images"
        onClick={() => {
          setIsSelecting(!isSelecting);
        }}
        checked={isSelecting}
      >
        <SelectImagesForm />
      </SidebarToggle>

      <SidebarToggle
        icon={SparklesIcon}
        label="Random sample"
        onClick={() => {
          if (mode === ImageListMode.RANDOM) {
            setModeBrowse();
          } else {
            setModeRandom();
          }
        }}
        checked={mode === ImageListMode.RANDOM}
      >
        <RandomModeForm />
      </SidebarToggle>

      <SidebarToggle
        icon={MagnifyingGlassIcon}
        label="Search"
        onClick={() => {
          if (mode === ImageListMode.SIMILAR) {
            setModeBrowse();
            setIsSearchOpen(false);
          } else {
            setIsFilterOpen(false);
            resetFilters();
            setIsSearchOpen(!isSearchOpen);
          }
        }}
        checked={isSearchOpen || mode === ImageListMode.SIMILAR}
      >
        <SearchForm />
      </SidebarToggle>

      <SidebarToggle
        icon={FunnelIcon}
        label="Filter"
        onClick={() => {
          setIsSearchOpen(false);
          if (mode === ImageListMode.SIMILAR) {
            setModeBrowse();
          }
          if (isFilterOpen) {
            resetFilters();
          }
          setIsFilterOpen(!isFilterOpen);
        }}
        checked={isFilterOpen}
      >
        <Filters />
      </SidebarToggle>
    </div>
  );
};
