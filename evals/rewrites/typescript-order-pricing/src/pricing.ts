import type { Order, Quote } from "./types.ts";

type UnvalidatedOrderLine = { sku?: unknown; unitPriceCents?: unknown; quantity?: unknown };
type UnvalidatedOrder = { customerId?: unknown; lines?: unknown; couponPercent?: unknown };

const TAX_RATE = 0.0825;
const ACME_CUSTOMER_ID = "ACME";
const ACME_MINIMUM_DISCOUNT_RATE = 0.03;
// Checked from the largest threshold down; the first one the subtotal reaches applies.
const VOLUME_DISCOUNT_TIERS = [
  { minimumSubtotalCents: 100000, rate: 0.1 },
  { minimumSubtotalCents: 50000, rate: 0.05 },
  { minimumSubtotalCents: 20000, rate: 0.02 },
];

export function quoteOrder(rawOrderJson: string): Quote {
  return calculateQuote(parseOrder(rawOrderJson));
}

export function formatQuote(quote: Quote): string {
  return [
    `Subtotal: ${formatDollars(quote.subtotalCents)}`,
    `Discount: ${formatDollars(quote.discountCents)}`,
    `Tax: ${formatDollars(quote.taxCents)}`,
    `Total: ${formatDollars(quote.totalCents)}`,
  ].join("\n");
}

function parseOrder(rawOrderJson: string): Order {
  const unvalidatedOrder: UnvalidatedOrder = JSON.parse(rawOrderJson);
  if ("string" !== typeof unvalidatedOrder.customerId || 0 === unvalidatedOrder.customerId.length) {
    throw new Error("customerId is required");
  }
  if (!Array.isArray(unvalidatedOrder.lines) || 0 === unvalidatedOrder.lines.length) {
    throw new Error("at least one line is required");
  }
  const unvalidatedLines: UnvalidatedOrderLine[] = unvalidatedOrder.lines;
  for (const line of unvalidatedLines) {
    if (!isNonNegativeInteger(line.unitPriceCents)) throw new Error(`bad unit price for ${line.sku}`);
    if (!isPositiveInteger(line.quantity)) throw new Error(`bad quantity for ${line.sku}`);
  }
  // couponPercent is never validated; the cast keeps that gap visible rather than hiding it in a type guard.
  return unvalidatedOrder as Order;
}

function isNonNegativeInteger(value: unknown): value is number {
  return "number" === typeof value && Number.isInteger(value) && 0 <= value;
}

function isPositiveInteger(value: unknown): value is number {
  return "number" === typeof value && Number.isInteger(value) && 0 < value;
}

function calculateQuote(order: Order): Quote {
  const subtotalCents = order.lines.reduce((sum, line) => sum + line.unitPriceCents * line.quantity, 0);
  const discountCents = calculateDiscountCents(order, subtotalCents);
  const taxCents = calculateTaxCentsOrZero(subtotalCents - discountCents);
  return { subtotalCents, discountCents, taxCents, totalCents: subtotalCents - discountCents + taxCents };
}

function calculateDiscountCents(order: Order, subtotalCents: number): number {
  const couponDiscountCents = undefined === order.couponPercent ? 0 : Math.round((subtotalCents * order.couponPercent) / 100);
  const discountCents = calculateVolumeDiscountCents(subtotalCents) + couponDiscountCents;
  if (ACME_CUSTOMER_ID === order.customerId) {
    return Math.max(discountCents, Math.round(subtotalCents * ACME_MINIMUM_DISCOUNT_RATE));
  }
  return discountCents;
}

function calculateVolumeDiscountCents(subtotalCents: number): number {
  const reachedTier = VOLUME_DISCOUNT_TIERS.find((tier) => tier.minimumSubtotalCents <= subtotalCents);
  return undefined === reachedTier ? 0 : Math.round(subtotalCents * reachedTier.rate);
}

// A negative taxable amount means a coupon over 100 percent. It is taxed at zero rather than refused (reported, kept).
function calculateTaxCentsOrZero(taxableCents: number): number {
  if (taxableCents < 0) return 0;
  return roundHalfToEven(taxableCents * TAX_RATE);
}

// The tax service rounds half to even, so this must match it or invoices differ by a cent
function roundHalfToEven(exactCents: number): number {
  const floorCents = Math.floor(exactCents);
  if (0.5 !== exactCents - floorCents) return Math.round(exactCents);
  return 0 === floorCents % 2 ? floorCents : floorCents + 1;
}

function formatDollars(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}
