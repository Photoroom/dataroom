import React, { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { MainContainer } from "../layouts/MainContainer";
import { GroupTypesFilterSidebar } from "../layouts/groups/GroupTypesFilterSidebar";
import { useGroupTypesList } from "../api/client";
import { toast } from "react-hot-toast";
import { Card } from "../components/common/Card";
import { LoaderSkeleton } from "../components/common/LoaderSkeleton";
import { GroupTypeCard } from "../components/group/GroupTypeCard";

const readCsv = (v: string | null): string[] | undefined => {
  if (!v) return undefined;
  const arr = v.split(",").filter(Boolean);
  return arr.length ? arr : undefined;
};

export const GroupTypeListPage: React.FC = function () {
  const [searchParams] = useSearchParams();
  const params = {
    name__prefix: searchParams.get("name__prefix") || undefined,
    // plain selection: the type declares the role, required or optional
    roles: readCsv(searchParams.get("roles")),
    required_roles: readCsv(searchParams.get("required_roles")),
    // legacy URLs from the pre-`roles` picker still filter
    optional_roles: readCsv(searchParams.get("optional_roles")),
  };
  const anyFilter = Boolean(params.name__prefix) || params.roles || params.required_roles || params.optional_roles;

  const { data: groupTypes, isLoading, isError } = useGroupTypesList(params);

  useEffect(() => {
    if (isError) {
      toast.error("Error loading group types");
    }
  }, [isError]);

  const results = groupTypes?.results ?? [];

  return (
    <>
      <GroupTypesFilterSidebar />
      <MainContainer isDrawerOpen={false} isSidebarOpen>
        <div className="flex flex-col">
          {isLoading && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2 p-2 sm:gap-4 sm:p-4">
              {Array.from({ length: 15 }).map((_, i) => (
                <Card key={i} className="flex-col">
                  <div className="flex flex-col gap-2 p-3">
                    <LoaderSkeleton className="h-4 w-3/4" />
                    <LoaderSkeleton className="h-3 w-1/2" />
                  </div>
                </Card>
              ))}
            </div>
          )}
          {!isLoading && results.length === 0 && (
            <p className="text-sm opacity-50 p-4">
              {anyFilter ? "No group types match these filters." : "No group types yet."}
            </p>
          )}
          {!isLoading && results.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2 p-2 sm:gap-4 sm:p-4">
              {results.map(gt => (
                <GroupTypeCard key={gt.name} groupType={gt} />
              ))}
            </div>
          )}
        </div>
      </MainContainer>
    </>
  );
};
