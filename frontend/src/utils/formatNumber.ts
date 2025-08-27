type FormatNumberOptions = {
  thousandsSeparator?: string;
  decimals?: number;
};

export function formatNumber(
  number: number | string | undefined | null,
  { thousandsSeparator = ",", decimals = 2 }: FormatNumberOptions = {}
): string {
  if (number === undefined || number === null) return "";
  if (typeof number === "string") {
    number = parseFloat(number);
  }

  // Split number into whole and decimal parts
  let [wholePart, decimalPart] = number.toFixed(decimals).split(".");

  // Add thousand separators only to the whole part
  const formattedWholePart = wholePart.replace(/\B(?=(\d{3})+(?!\d))/g, thousandsSeparator);

  // Combine whole and decimal parts (only if decimals > 0)
  let formattedNumber = decimals > 0 && decimalPart ? `${formattedWholePart}.${decimalPart}` : formattedWholePart;

  return formattedNumber;
}
