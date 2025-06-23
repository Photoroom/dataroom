import React, {useEffect, useRef} from 'react';

interface TagInputProps {
  value: string[];
  onChange: (value: string[]) => void;
  options?: string[];
  placeholder?: string;
}

export const TagInput: React.FC<TagInputProps> = (props) => {
  const {
    value = [],
    onChange = () => {},
    options = [],
    placeholder,
  } = props;
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const blurListener = addTag;

    inputRef.current?.addEventListener('blur-sm', blurListener);

    return () => {
      inputRef.current?.removeEventListener('blur-sm', blurListener);
    };
  }, []);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    const { key } = event;

    if (['Enter', 'Tab', ' ', ','].includes(key)) {
      event.preventDefault();
      addTag();
    }

    if (key === 'Backspace') {
      if (!inputRef.current) {
        return;
      }
      const newTagValue = inputRef.current.value;

      if (!newTagValue.trim().length) {
        onChange(value.slice(0, value.length - 1));
      }
    }
  };

  function addTag() {
    if (!inputRef.current) {
      return;
    }

    let newTagValue = inputRef.current.value;
    newTagValue = newTagValue.trim();

    if (!newTagValue.length) {
      return;
    }
    if (value.includes(newTagValue)) {
      return;
    }

    inputRef.current.value = '';
    onChange([...value, newTagValue]);
  }

  function removeTag(removedTag: string) {
    onChange(value.filter((tag) => tag !== removedTag));
  }

  function focusOnInput() {
    if (!inputRef.current) {
      return;
    }
    inputRef.current.focus();
  }

  return (
    <div className="flex flex-row flex-wrap gap-1 items-center px-2 py-1 rounded-xl min-h-[48px] border border-black/20 dark:border-white/20" onClick={focusOnInput}>
      {value?.map((tag) => (
        <span className="relative pr-8 pl-3 py-1 rounded-full text-xs text-left bg-black/8 dark:bg-white/8" key={tag}>
          {tag}
          <button className="absolute right-0 top-0 bottom-0 rounded-r-full size-6 cursor-pointer hover:text-red-500 hover:bg-black/8 dark:hover:bg-white/8" onClick={() => removeTag(tag)}>&times;</button>
        </span>
      ))}

      <input className="grow border-0 bg-transparent px-2 h-[32px] outline-0 ring-0 focus:border-0 focus:outline-0 focus:ring-0" type="text" onKeyDown={onKeyDown} ref={inputRef} list="tags" placeholder={placeholder} />

      <datalist id="tags">
        {options.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </datalist>
    </div>
  );
};
