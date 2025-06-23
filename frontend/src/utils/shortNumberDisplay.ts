
export function shortNumberDisplay(number : number | null | undefined) : string {
    if (number === null || number === undefined) return "";
    if (number < 1000) return number.toString();
    let digits = 0;
    let suffix = "";

    if (number >= 1000000000) {
      digits = (number / 1000000000);
      suffix = "B";
    } else if (number >= 1000000) {
      digits = (number / 1000000);
      suffix = "M";
    } else if (number >= 1000) {
      digits = (number / 1000);
      suffix = "K";
    } else {
      return String(number);
    }

    return digits.toFixed(digits >= 10 ? 0 : 1) + suffix;
}
