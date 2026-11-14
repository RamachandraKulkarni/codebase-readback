import type { Order } from "./types.ts";

// Maps the order to the internal order
export function mapOrderToInternalOrder(order: Order): Order {
  return {
    customerId: order.customerId,
    lines: order.lines.map((l) => ({ sku: l.sku, unitPriceCents: l.unitPriceCents, quantity: l.quantity })),
    couponPercent: order.couponPercent,
  };
}
