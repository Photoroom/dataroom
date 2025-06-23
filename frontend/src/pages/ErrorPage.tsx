import { useRouteError } from "react-router-dom";
import {ExclamationTriangleIcon} from "@heroicons/react/24/outline";

export function ErrorPage() {
  const error = useRouteError() as any;
  console.error(error);

  return (
    <div className="text-center my-20">
      <p className="mb-3"><ExclamationTriangleIcon className="w-12 h-12 mx-auto" /></p>
      <p className="text-3xl mb-3">{error.status}</p>
      <p className="">{error.statusText || error.message || 'Sorry, something went wrong'}</p>
    </div>
  );
}
