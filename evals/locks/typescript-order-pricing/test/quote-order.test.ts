// Characterization tests: they record what the module does today, bugs included, so a rewrite can prove it changed nothing.
import { describe, expect, it } from "vitest";
import { formatQuote, quoteOrder } from "../src/index.ts";

const orderOfOneLine = (unitPriceCents: number, quantity = 1, extraFields: Record<string, unknown> = {}) =>
  JSON.stringify({ customerId: "C-9", lines: [{ sku: "x", unitPriceCents, quantity }], ...extraFields });

const orderForCustomer = (customerId: string, unitPriceCents: number) =>
  JSON.stringify({ customerId, lines: [{ sku: "d", unitPriceCents, quantity: 1 }] });

describe("quoteOrder volume discount tiers", () => {
  it.each([
    ["no discount below 20000", orderOfOneLine(19999), { subtotalCents: 19999, discountCents: 0, taxCents: 1650, totalCents: 21649 }],
    ["2% from 20000", orderOfOneLine(20000), { subtotalCents: 20000, discountCents: 400, taxCents: 1617, totalCents: 21217 }],
    ["2% just below 50000", orderOfOneLine(49999), { subtotalCents: 49999, discountCents: 1000, taxCents: 4042, totalCents: 53041 }],
    ["5% from 50000", orderOfOneLine(50000), { subtotalCents: 50000, discountCents: 2500, taxCents: 3919, totalCents: 51419 }],
    ["5% just below 100000", orderOfOneLine(99999), { subtotalCents: 99999, discountCents: 5000, taxCents: 7837, totalCents: 102836 }],
    ["10% from 100000", orderOfOneLine(100000), { subtotalCents: 100000, discountCents: 10000, taxCents: 7425, totalCents: 97425 }],
  ])("%s", (_caseName, orderJson, expectedQuote) => {
    expect(quoteOrder(orderJson)).toEqual(expectedQuote);
  });
});

describe("quoteOrder coupons and customers", () => {
  it("adds the coupon on top of the volume discount", () => {
    expect(quoteOrder(orderOfOneLine(12000, 10, { couponPercent: 10 })))
      .toEqual({ subtotalCents: 120000, discountCents: 24000, taxCents: 7920, totalCents: 103920 });
  });

  it("treats a zero coupon as no coupon", () => {
    expect(quoteOrder(orderOfOneLine(30000, 1, { couponPercent: 0 })))
      .toEqual({ subtotalCents: 30000, discountCents: 600, taxCents: 2426, totalCents: 31826 });
  });

  it.each([
    ["ACME gets 3% where the tier gives less", orderForCustomer("ACME", 45000), { subtotalCents: 45000, discountCents: 1350, taxCents: 3601, totalCents: 47251 }],
    ["ACME keeps the tier when it is larger", orderForCustomer("ACME", 150000), { subtotalCents: 150000, discountCents: 15000, taxCents: 11138, totalCents: 146138 }],
    ["ACME gets 3% below every tier", orderForCustomer("ACME", 1000), { subtotalCents: 1000, discountCents: 30, taxCents: 80, totalCents: 1050 }],
    ["ACME minimum compares against volume plus coupon", JSON.stringify({ customerId: "ACME", lines: [{ sku: "d", unitPriceCents: 30000, quantity: 1 }], couponPercent: 2 }), { subtotalCents: 30000, discountCents: 1200, taxCents: 2376, totalCents: 31176 }],
    ["other customers get no minimum", orderForCustomer("ACME-2", 1000), { subtotalCents: 1000, discountCents: 0, taxCents: 82, totalCents: 1082 }],
  ])("%s", (_caseName, orderJson, expectedQuote) => {
    expect(quoteOrder(orderJson)).toEqual(expectedQuote);
  });

  it("pins a known bug: a coupon over 100 percent gives zero tax and a negative total", () => {
    expect(quoteOrder(orderOfOneLine(3000, 1, { couponPercent: 150 })))
      .toEqual({ subtotalCents: 3000, discountCents: 4500, taxCents: 0, totalCents: -1500 });
  });
});

describe("quoteOrder tax rounding", () => {
  it("rounds an exact half cent down to the even cent", () => {
    expect(quoteOrder(orderOfOneLine(200)).taxCents).toBe(16);
  });

  it("rounds an exact half cent up to the even cent", () => {
    expect(quoteOrder(orderOfOneLine(600)).taxCents).toBe(50);
  });

  it("sums every line, including free ones", () => {
    const orderJson = JSON.stringify({
      customerId: "C-4",
      lines: [
        { sku: "a", unitPriceCents: 199, quantity: 3 },
        { sku: "b", unitPriceCents: 1050, quantity: 2 },
        { sku: "c", unitPriceCents: 0, quantity: 7 },
      ],
    });
    expect(quoteOrder(orderJson)).toEqual({ subtotalCents: 2697, discountCents: 0, taxCents: 223, totalCents: 2920 });
  });
});

describe("quoteOrder input validation", () => {
  it.each([
    ["missing customerId", '{"lines":[{"sku":"a","unitPriceCents":1,"quantity":1}]}', "customerId is required"],
    ["empty customerId", '{"customerId":"","lines":[{"sku":"a","unitPriceCents":1,"quantity":1}]}', "customerId is required"],
    ["numeric customerId", '{"customerId":7,"lines":[{"sku":"a","unitPriceCents":1,"quantity":1}]}', "customerId is required"],
    ["missing lines", '{"customerId":"C"}', "at least one line is required"],
    ["empty lines", '{"customerId":"C","lines":[]}', "at least one line is required"],
    ["negative unit price", '{"customerId":"C","lines":[{"sku":"a","unitPriceCents":-1,"quantity":1}]}', "bad unit price for a"],
    ["fractional unit price", '{"customerId":"C","lines":[{"sku":"a","unitPriceCents":1.5,"quantity":1}]}', "bad unit price for a"],
    ["zero quantity", '{"customerId":"C","lines":[{"sku":"a","unitPriceCents":1,"quantity":0}]}', "bad quantity for a"],
    ["fractional quantity", '{"customerId":"C","lines":[{"sku":"a","unitPriceCents":1,"quantity":2.5}]}', "bad quantity for a"],
  ])("refuses %s", (_caseName, orderJson, expectedMessage) => {
    expect(() => quoteOrder(orderJson)).toThrow(new Error(expectedMessage));
  });

  it("lets a JSON syntax error through unchanged", () => {
    expect(() => quoteOrder("not json")).toThrow(SyntaxError);
  });

  it("accepts a zero unit price", () => {
    expect(quoteOrder(orderOfOneLine(0)).totalCents).toBe(0);
  });
});

describe("formatQuote", () => {
  it("prints dollars with two decimals, one field per line", () => {
    expect(formatQuote({ subtotalCents: 45000, discountCents: 1350, taxCents: 3601, totalCents: 47251 }))
      .toBe("Subtotal: $450.00\nDiscount: $13.50\nTax: $36.01\nTotal: $472.51");
  });

  it("puts the minus sign after the dollar sign", () => {
    expect(formatQuote({ subtotalCents: 3000, discountCents: 4500, taxCents: 0, totalCents: -1500 }))
      .toBe("Subtotal: $30.00\nDiscount: $45.00\nTax: $0.00\nTotal: $-15.00");
  });

  it("prints thousands without separators", () => {
    expect(formatQuote({ subtotalCents: 123456789, discountCents: 100000, taxCents: 0, totalCents: 123356789 }))
      .toBe("Subtotal: $1234567.89\nDiscount: $1000.00\nTax: $0.00\nTotal: $1233567.89");
  });

  it("rounds sub-cent values the way toFixed does", () => {
    expect(formatQuote({ subtotalCents: 1, discountCents: 5, taxCents: 105, totalCents: 99999 }))
      .toBe("Subtotal: $0.01\nDiscount: $0.05\nTax: $1.05\nTotal: $999.99");
  });
});
