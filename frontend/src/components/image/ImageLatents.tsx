import React from "react";
import { CodeBracketSquareIcon, Square3Stack3DIcon } from "@heroicons/react/24/outline";
import { OSImage } from "../../api/client.schemas";
// import ImageSegmentation from "./ImageSegmentation";
import { Collapsible } from "../common/Collapsible";

interface ImageLatentsProps {
  image?: OSImage;
}

export const ImageLatents: React.FC<ImageLatentsProps> = ({ image }) => {
  return (
    <Collapsible name="latents" title="Latents">
      <div className="grid grid-cols-1 gap-2">
        {image ? (
          <>
            {image.latents?.map(latent => (
              <a
                key={latent.latent_type}
                href={latent.file_direct_url}
                target="_blank"
                className="group flex flex-row items-center gap-2 text-sm break-all"
              >
                {latent.is_mask ? (
                  <Square3Stack3DIcon className="size-6" />
                ) : (
                  <CodeBracketSquareIcon className="size-6" />
                )}
                <span className="group-hover:underline">{latent.latent_type}</span>
              </a>
            ))}
            {image.latents?.length === 0 && <p className="opacity-50">No latents</p>}
          </>
        ) : (
          <></>
        )}
      </div>
    </Collapsible>
  );
};
