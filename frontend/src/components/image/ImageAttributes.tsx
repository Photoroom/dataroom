import React from "react";
import defaultValue from "../../utils/defaultValue";
import { JsonView } from "../common/JsonView";
import { OSImage } from "../../api/client.schemas";
import { Collapsible } from "../common/Collapsible";
import { LoaderSkeleton } from "../common/LoaderSkeleton";

interface ImageAttributesProps {
  image?: OSImage;
}

export const ImageAttributes: React.FC<ImageAttributesProps> = ({ image }) => {
  type Primitive = string | number | boolean | null | undefined;
  const isPrimitive = (v: unknown): v is Primitive => v == null || ["string", "number", "boolean"].includes(typeof v);

  const renderValue = (value: unknown): React.ReactNode => {
    if (isPrimitive(value)) {
      return defaultValue(value);
    }
    if (Array.isArray(value)) {
      const allPrimitive = value.every(isPrimitive);
      if (allPrimitive) {
        const arr = value as Primitive[];
        const str = arr.map(v => defaultValue(v)).join(", ");
        // Collapse long primitive arrays behind Show/Hide
        if (str.length > 100 || arr.length > 10) {
          return <JsonView value={arr} initiallyCollapsed={true} />;
        }
        return str;
      }
      return <JsonView value={value} initiallyCollapsed={true} />;
    }
    if (typeof value === "object") {
      return <JsonView value={value} initiallyCollapsed={true} />;
    }
    return String(value as unknown as string);
  };
  return (
    <Collapsible name="attributes" title="Attributes" initialOpen={true}>
      <div className="grid grid-cols-5 gap-2">
        {image ? (
          <>
            {image.attributes &&
              Object.entries(image.attributes).map(([key, value]) => (
                <React.Fragment key={key}>
                  <p className="text-sm break-all col-span-2">{key}</p>
                  <div className="text-sm break-all col-span-3">{renderValue(value)}</div>
                </React.Fragment>
              ))}
            {!image.attributes ||
              (Object.keys(image.attributes).length === 0 && <p className="opacity-50 col-span-5">No attributes</p>)}
          </>
        ) : (
          <>
            {Array(4)
              .fill(null)
              .map((_, index) => (
                <React.Fragment key={index}>
                  <LoaderSkeleton className="col-span-2" />
                  <LoaderSkeleton className="col-span-3" />
                </React.Fragment>
              ))}
          </>
        )}
      </div>
    </Collapsible>
  );
};
