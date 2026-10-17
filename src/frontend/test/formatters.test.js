import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { toRoman } from "../src/lib/toRoman.js";

describe("toRoman converter", () => {
  it("converts positive integers to Roman numerals", () => {
    assert.strictEqual(toRoman(13), "XIII");
    assert.strictEqual(toRoman(15), "XV");
    assert.strictEqual(toRoman(16), "XVI");
    assert.strictEqual(toRoman(20), "XX");
  });

  it("handles string representations of numbers", () => {
    assert.strictEqual(toRoman("13"), "XIII");
    assert.strictEqual(toRoman("15"), "XV");
    assert.strictEqual(toRoman("16"), "XVI");
    assert.strictEqual(toRoman("20"), "XX");
  });

  it("handles standard edge cases", () => {
    assert.strictEqual(toRoman(1), "I");
    assert.strictEqual(toRoman(4), "IV");
    assert.strictEqual(toRoman(9), "IX");
    assert.strictEqual(toRoman(14), "XIV");
    assert.strictEqual(toRoman(0), "0");
    assert.strictEqual(toRoman(-5), "-5");
    assert.strictEqual(toRoman("abc"), "abc");
  });
});
