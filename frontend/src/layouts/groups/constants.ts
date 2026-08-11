// Type/role filter pickers fetch their whole catalogue once and filter
// in-memory. This is the page size requested (= the API's max page size); if a
// catalogue ever exceeds it the picker shows a truncation warning.
export const PICKER_PAGE_SIZE = 2000;
