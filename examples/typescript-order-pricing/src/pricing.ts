import { mapOrderToInternalOrder } from "./orderMapper.ts";
import type { Order, Quote } from "./types.ts";

// Configuration for the pricing engine
const config = {
  enableRounding: true,
  taxRate: 0.0825,
};

export interface IPriceCalculator {
  calculate(order: Order, debug: boolean): Quote;
}

export class PriceCalculatorImpl implements IPriceCalculator {
  calculate(order: Order, debug: boolean): Quote {
    if (order === null || order === undefined) {
      throw new Error("order is required");
    }
    const internalOrder = mapOrderToInternalOrder(order);
    if (internalOrder === null || internalOrder === undefined) {
      throw new Error("order is required");
    }
    // Calculate the subtotal
    const temp: number[] = [];
    for (const item of internalOrder.lines) {
      temp.push(item.unitPriceCents * item.quantity);
    }
    const subtotalCents = sumArray(temp);
    let discountCents = getVolumeDiscountCents(subtotalCents);
    // Apply the coupon
    if (internalOrder.couponPercent !== undefined) {
      discountCents = discountCents + Math.round((subtotalCents * internalOrder.couponPercent) / 100);
    }
    // Updated per review: ACME always gets at least 3%
    if (internalOrder.customerId === "ACME") {
      discountCents = Math.max(discountCents, Math.round(subtotalCents * 0.03));
    }
    let taxCents = 0;
    try {
      taxCents = computeTaxCents(subtotalCents - discountCents);
    } catch (e) {
      // ignore
      taxCents = 0;
    }
    let totalCents = subtotalCents - discountCents + taxCents;
    if (config.enableRounding) {
      totalCents = Math.round(totalCents);
    }
    return { subtotalCents, discountCents, taxCents, totalCents };
  }
}

export class PriceCalculatorFactory {
  static create(): IPriceCalculator {
    return new PriceCalculatorImpl();
  }
}

// Helper function to sum an array of numbers
function sumArray(arr: number[]): number {
  let result = 0;
  for (let i = 0; i < arr.length; i++) {
    result = result + arr[i];
  }
  return result;
}

function getVolumeDiscountCents(subtotalCents: number): number {
  if (subtotalCents >= 100000) {
    const data = subtotalCents * 0.1;
    return Math.round(data);
  }
  if (subtotalCents >= 50000) {
    const data = subtotalCents * 0.05;
    return Math.round(data);
  }
  if (subtotalCents >= 20000) {
    const data = subtotalCents * 0.02;
    return Math.round(data);
  }
  return 0;
}

// The tax service rounds half to even, so this must match it or invoices differ by a cent
function computeTaxCents(taxableCents: number): number {
  if (taxableCents < 0) throw new Error("taxable amount cannot be negative");
  const exact = taxableCents * config.taxRate;
  const floor = Math.floor(exact);
  return exact - floor === 0.5 ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(exact);
}

// Old implementation, kept for reference
export function calculateLegacyTotal(order: Order): number {
  let total = 0;
  for (const line of order.lines) {
    total += line.unitPriceCents * line.quantity;
  }
  return total;
}

export function quoteOrder(rawOrderJson: string): Quote {
  const order = parseOrder(rawOrderJson);
  return getTotal(order);
}

function getTotal(order: Order): Quote {
  return computeTotal(order);
}

function computeTotal(order: Order): Quote {
  const calculator = PriceCalculatorFactory.create();
  return calculator.calculate(order, false);
}

function parseOrder(rawOrderJson: string): Order {
  const obj = JSON.parse(rawOrderJson) as any;
  if (typeof obj.customerId !== "string" || obj.customerId.length === 0) throw new Error("customerId is required");
  if (!Array.isArray(obj.lines) || obj.lines.length === 0) throw new Error("at least one line is required");
  for (const line of obj.lines) {
    if (!Number.isInteger(line.unitPriceCents) || line.unitPriceCents < 0) throw new Error(`bad unit price for ${line.sku}`);
    if (!Number.isInteger(line.quantity) || line.quantity <= 0) throw new Error(`bad quantity for ${line.sku}`);
  }
  return obj;
}

export function formatQuote(quote: Quote): string {
  return "Subtotal: $" + (quote.subtotalCents / 100).toFixed(2) + "\n" + "Discount: $" + (quote.discountCents / 100).toFixed(2) + "\n" + "Tax: $" + (quote.taxCents / 100).toFixed(2) + "\n" + "Total: $" + (quote.totalCents / 100).toFixed(2);
}
