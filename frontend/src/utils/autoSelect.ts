// One-shot handshake between "add groups to this dataset" entry points and the
// groups toolbar: the link marks the flag, the toolbar consumes it on arrival
// and opens selection mode. sessionStorage instead of a query param because
// ImageListDataContext owns the whole URL query string and would resurrect a
// stripped param from its own snapshot.
const AUTO_SELECT_FLAG = "groups:autoSelect";

export const markAutoSelect = () => sessionStorage.setItem(AUTO_SELECT_FLAG, "1");

/** True exactly once per mark — reading clears the flag. */
export const consumeAutoSelect = () => {
  const set = sessionStorage.getItem(AUTO_SELECT_FLAG) === "1";
  if (set) sessionStorage.removeItem(AUTO_SELECT_FLAG);
  return set;
};
