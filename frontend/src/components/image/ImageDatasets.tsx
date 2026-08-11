import React from "react";
import { Link } from "react-router-dom";
import { OSImage } from "../../api/client.schemas";
import { Collapsible } from "../common/Collapsible";
import { URLS } from "../../urls";

interface ImageDatasetsProps {
  image?: OSImage;
}

// `datasets` is derived from dataset membership (Dataset -> Group -> image) and
// carried on the image document as ["<slug>/<version>", ...]. Read-only here:
// membership is edited through groups, never on the image.
export const ImageDatasets: React.FC<ImageDatasetsProps> = ({ image }) => {
  const datasets = image?.datasets ?? [];

  return (
    <Collapsible name="datasets" title="Datasets">
      <div className="flex flex-row flex-wrap items-center gap-1.5 text-xs">
        {datasets.length === 0 && <p className="opacity-50">Not in any dataset</p>}
        {datasets.map(slugVersion => {
          const [slug, version] = slugVersion.split("/");
          return (
            <Link
              key={slugVersion}
              to={URLS.DATASET_DETAIL(slug, version)}
              title={`Open dataset ${slugVersion}`}
              className="px-2 py-0.5 rounded-full bg-black/8 dark:bg-white/8 hover:bg-black/15 dark:hover:bg-white/15 transition-colors font-mono"
            >
              {slugVersion}
            </Link>
          );
        })}
      </div>
    </Collapsible>
  );
};
