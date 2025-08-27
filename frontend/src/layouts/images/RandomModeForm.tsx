import React from "react";
import { useImageListData } from "../../context/ImageListDataContext";
import { NumberField } from "../../components/forms/NumberField";

export const RandomModeForm: React.FC = () => {
  const { randomPrefixLength, setRandomPrefixLength, randomNumPrefixes, setRandomNumPrefixes } = useImageListData();

  return (
    <div className="flex flex-row gap-2">
      <NumberField
        name="prefix_length"
        label="prefix_length"
        helpText="Filter image_hash by a number of random prefixes. A smaller prefix_length will give you more samples, but less random."
        value={randomPrefixLength}
        onChange={e => {
          setRandomPrefixLength(Number(e.target.value));
        }}
      />
      <NumberField
        name="num_prefixes"
        label="num_prefixes"
        helpText="Filter image_hash by a number of random prefixes. A higher num_prefixes will give you more samples, but slow down the query."
        value={randomNumPrefixes}
        onChange={e => {
          setRandomNumPrefixes(Number(e.target.value));
        }}
      />
    </div>
  );
};
