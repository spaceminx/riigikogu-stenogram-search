export function toRoman(num) {
  const n = parseInt(num, 10);
  if (isNaN(n) || n <= 0) return num != null ? String(num) : "";
  const lookup = [
    [1000, "M"],
    [900, "CM"],
    [500, "D"],
    [400, "CD"],
    [100, "C"],
    [90, "XC"],
    [50, "L"],
    [40, "XL"],
    [10, "X"],
    [9, "IX"],
    [5, "V"],
    [4, "IV"],
    [1, "I"],
  ];
  let result = "";
  let rem = n;
  for (const [val, roman] of lookup) {
    while (rem >= val) {
      result += roman;
      rem -= val;
    }
  }
  return result;
}
