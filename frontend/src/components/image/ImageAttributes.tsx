import React from "react";
import defaultValue from "../../utils/defaultValue";
import { OSImage } from "../../api/client.schemas";
import { Collapsible } from "../common/Collapsible";
import { LoaderSkeleton } from "../common/LoaderSkeleton";

interface ImageAttributesProps {
  image?: OSImage;
}

export const ImageAttributes: React.FC<ImageAttributesProps> = ({ image }) => {
  return (
    <Collapsible name="attributes" title="Attributes" initialOpen={true}>
      <div className="grid grid-cols-5 gap-2">
        {
          image ? (
            <>
              {image.attributes && Object.entries(image.attributes).map(([key, value]) => (
                <React.Fragment key={key}>
                  <p className="text-sm break-all col-span-2">{key}</p>
                  <p className="text-sm break-all col-span-3">{defaultValue(value)}</p>
                </React.Fragment>
              ))}
              {!image.attributes || Object.keys(image.attributes).length === 0 && (
                <p className="opacity-50 col-span-5">No attributes</p>
              )}
            </>
          ) : (
            <>
              {Array(4).fill(null).map((_, index) => (
                <React.Fragment key={index}>
                  <LoaderSkeleton className="col-span-2" />
                  <LoaderSkeleton className="col-span-3" />
                </React.Fragment>
              ))}
            </>
          )
        }
      </div>
    </Collapsible>
  );
}; 
